#!/usr/bin/env python

# Copyright (C) 2017 Pier Carlo Chiodi
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import ipaddr
import itertools
import random
import struct
import time

from pierky.usres_monitor import UniqueSmallestRoutableEntriesMonitor, \
                                 USRESMonitorException

usres_monitor = None

def new_usres(ip_ver, target_prefix_len):
    global usres_monitor
    usres_monitor = UniqueSmallestRoutableEntriesMonitor(
        target_prefix_len4=target_prefix_len if ip_ver == 4 else 24,
        target_prefix_len6=target_prefix_len if ip_ver == 6 else 40,
        force_sqlite_lib=sqlite_lib
    )

def test_outcome(func, descr, result):
    print("{:<15}: {:>40}: {}".format(func, descr, result))

def print_rs(sql):
    rs = usres_monitor.sql_out(sql).fetchall()
    for r in rs:
        print(r)

def test_min_max(net_str, target_prefix_len, exp_first, exp_last,
                 shoud_fail=False):
    failed = False
    try:
        net = ipaddr.IPNetwork(net_str)

#        assert net_str.lower() == "{}/{}".format(exp_first, net.prefixlen), \
#               ("String representations of original net and first expected "
#                "prefix don't match.")

        min_int, max_int, _ = usres_monitor.get_sre(net, target_prefix_len)
        first = usres_monitor.get_ip_repr(net.version, min_int)
        last = usres_monitor.get_ip_repr(net.version, max_int)

        res = "{}/{}".format(first, target_prefix_len)
        exp = "{}/{}".format(exp_first.lower(), target_prefix_len)
        assert res == exp, \
               ("First expected prefix doesn't match: {} vs {}".format(
                   res, exp)
               )

        res = "{}/{}".format(last, target_prefix_len)
        exp = "{}/{}".format(exp_last.lower(), target_prefix_len)
        assert res == exp, \
               ("Last expected prefix doesn't match: {} vs {}".format(
                   res, exp)
               )

    except AssertionError:
        failed = True
        if shoud_fail:
            pass
        else:
            raise

    assert shoud_fail == failed

    test_outcome("get_sre",
                 "{} in /{}".format(net_str, target_prefix_len),
                 "OK{}".format(" (failed as expected)" if shoud_fail else ""))

def test_duplicate(net_str, net2_str=None, dup_found=True):
    usres_monitor.add_net(ipaddr.IPNetwork(net_str))
    try:
        usres_monitor.add_net(
            ipaddr.IPNetwork(net2_str if net2_str else net_str)
        )
    except USRESMonitorException as e:
        if "it was already in the db" in str(e):
            test_outcome("test_duplicate",
                         "{} and {}".format(
                             net_str,
                             net2_str if net2_str else net_str),
                         "OK" if dup_found else "FAIL")
            if not dup_found:
                raise AssertionError("Duplicate found")
            return
    test_outcome("test_duplicate",
                    "{} and {}".format(
                        net_str,
                        net2_str if net2_str else net_str),
                    "FAIL" if dup_found else "OK")
    if dup_found:
        raise AssertionError("Duplicate not found")

def test_sre(prefixes, exp_results, clear=True,
             action_descr=None, print_details=True):
    if clear:
        print("-" * 80)
    else:
        print("")

    ip_ver = ipaddr.IPNetwork(prefixes[0][0]).version

    if action_descr:
        print(action_descr)

    for net_str, add_del in prefixes:
        net = ipaddr.IPNetwork(net_str)
        if add_del == "add":
            if not action_descr:
                print("adding {}...".format(net))
            usres_monitor.add_net(net)
        else:
            if not action_descr:
                print("removing {}...".format(net))
            usres_monitor.del_net(net)
    records = list(usres_monitor.get_prefixes(ip_ver))
        
    # only print the records
    for record in records:
        if print_details:
            print("{:<15}: {:>25} -> {:<25}, {:>5}".format(
                "{}/{}".format(
                    record["first_ip"],
                    record["pref_len"]),
                "{int_repr} {ip}".format(
                    int_repr=record["first_int"],
                    ip=record["first_ip"]),
                "{ip} {int_repr}".format(
                    int_repr=record["last_int"],
                    ip=record["last_ip"]),
                record["cnt"]
            ))

    try:
        # match records with expected results
        for record, exp_res in itertools.izip_longest(records, exp_results):
            assert exp_res is not None, \
                "Missing expected result for this record:"
            assert record["first_ip"] == exp_res[0], \
                ("The first net ID does not match with the expected one: "
                "db {}, exp {}".format(record["first_ip"], exp_res[0]))
            assert record["last_ip"] == exp_res[1], \
                ("The last net ID does not match with the expected one: "
                "db {}, exp {}".format(record["last_ip"], exp_res[1]))

        assert len(records) == len(exp_results), \
            ("The number of records ({}) is different from the number of "
            "expected results ({})".format(len(records), len(exp_results)))

    except Exception as e:
        print_rs("SELECT * FROM prefixes{ip_ver}".format(ip_ver=ip_ver))
        raise AssertionError("Record ID {} - {}".format(record["id"], str(e)))

    if not print_details:
        print(" \-- details omitted")
    test_outcome("test_sre", "", "OK")

def add_random_net(ip_ver, target_prefix_len):

    def dump_vars():
        print("target_prefix_len", target_prefix_len)
        print("prefix_len", prefix_len)
        print("max_prefix_len", max_prefix_len)
        print("max_range_len", max_range_len)
        print("max_range", max_range)
        print("rand", rand)
        print("net_id", net_id)
        print("ip", ip)
        print("net", net)
        print("str(net.ip)", str(net.ip))
        print("str(net.network)", str(net.network))

    if ip_ver == 4:
        prefix_len = random.randint(8, target_prefix_len-1)
        max_range_len = prefix_len
        max_prefix_len = 32
        ip_class = ipaddr.IPv4Address
        net_class = ipaddr.IPv4Network
    else:
        prefix_len = random.randint(19, target_prefix_len-1)
        max_range_len = prefix_len - 1 # to avoid overflow
        max_prefix_len = 64
        ip_class = ipaddr.IPv6Address
        net_class = ipaddr.IPv6Network

    max_range = 2**max_range_len - 1
    rand = random.randint(0, max_range)
    net_id = rand << max_prefix_len - prefix_len
    if ip_ver == 6:
        net_id = net_id << 64
    ip = ip_class(net_id)
    net = net_class("{}/{}".format(str(ip), prefix_len))

    try:
        assert str(net.ip) == str(net.network)
    except:
        dump_vars()
        raise

    try:
        usres_monitor.add_net(net)
    except USRESMonitorException as e:
        if "it was already in the db" in str(e):
            return "dup", net
    except:
        dump_vars()

    return "ok", net
 
def test_random_load(ip_ver, prefix_cnt, target_prefix_len):
    new_usres(ip_ver, target_prefix_len)
    res = {"dup": 0, "ok": 0}

    add_begin = int(time.time())
    for i in range(prefix_cnt):
        dup_ok, net = add_random_net(ip_ver, target_prefix_len)
        res[dup_ok] += 1
        if i % 10 == 0:
            usres_monitor.del_net(net)

    add_end = int(time.time())

    qry_begin = int(time.time())
    cnt = usres_monitor.get_count(ip_ver)
    qry_end = int(time.time())

    test_outcome("random_load",
                 "{} IPv{} prefixes, /{}".format(
                     prefix_cnt, ip_ver, target_prefix_len),
                 "OK ({} duplicate, {} SREs, add/del {}s, qry {}s)".format(
                     res["dup"], cnt, add_end-add_begin, qry_end-qry_begin)
                 )

def test_base():
    test_min_max("1.2.3.4/8", 24, "1.0.0.0", "1.255.255.0")
    test_min_max("255.0.0.0/8", 24, "255.0.0.0", "255.255.255.0")
    test_min_max("255.0.0.0/9", 24, "255.0.0.0", "255.127.255.0")
    test_min_max("2001:aaaa::/32", 48, "2001:aaaa::", "2001:aaaa:ffff::")
    test_min_max("192.168.0.1/32", 32, "192.168.0.1", "192.168.0.1")
    test_min_max("2001:db8::/64", 64, "2001:db8::", "2001:db8::")
    test_min_max("2001:db8::/63", 64, "2001:db8::", "2001:db8:0:1::")
    test_min_max("2001:db8::/60", 64, "2001:db8::", "2001:db8:0:f::")
    test_min_max("2000::/3", 64, "2000::", "3fff:ffff:ffff:ffff::")
    test_min_max("7fff:ffff:ffff:ffff::/64", 64,
                 "7fff:ffff:ffff:ffff::", "7fff:ffff:ffff:ffff::")
    test_min_max("8000:0000:0000:0000::/64", 64, "", "", shoud_fail=True)
    test_min_max("192.168.0.1/32", 24, "", "", shoud_fail=True)
    test_min_max("2001:db8::/60", 56, "", "", shoud_fail=True)
    test_min_max("2001:aaaa::/32", 65, "", "", shoud_fail=True)

    new_usres(4, 25)
    test_duplicate("192.0.2.0/24")
    test_duplicate("10.0.0.0/8", "10.0.0.0/24", dup_found=False)

    new_usres(6, 48)
    test_duplicate("2001:ffff::/32")

    new_usres(6, 64)
    test_duplicate("2001:bbbb::/32", "2001:bbbb::/56", dup_found=False)

def test_sres():
    # --------------------------------------------------------
    new_usres(4, 24)
    test_sre(
        [
            ("255.0.0.0/8", "add"),
            ("192.168.0.0/16", "add"),
            ("10.0.0.0/8", "add")
        ],
        [
            ("255.0.0.0", "255.255.255.0"),
            ("192.168.0.0", "192.168.255.0"),
            ("10.0.0.0", "10.255.255.0")
        ]
    )

    # --------------------------------------------------------
    new_usres(4, 24)
    test_sre(
        [
            ("255.0.0.0/8", "add"),
            ("255.255.0.0/16", "add"),
            ("10.0.0.0/8", "add")
        ],
        [
            ("255.0.0.0", "255.255.255.0"),
            ("10.0.0.0", "10.255.255.0")
        ]
    )

    # --------------------------------------------------------
    new_usres(4, 24)
    test_sre(
        [("255.0.0.0/8", "add")],
        [("255.0.0.0", "255.255.255.0")]
    )
    test_sre(
        [("255.255.0.0/16", "add")],
        [("255.0.0.0", "255.255.255.0"),],
        clear=False
    )
    test_sre(
        [("255.0.0.0/8", "del")],
        [("255.255.0.0", "255.255.255.0")],
        clear=False
    )

    # --------------------------------------------------------
    new_usres(4, 24)
    test_sre(
        [("255.0.0.0/8", "add")],
        [("255.0.0.0", "255.255.255.0")]
    )
    test_sre(
        [("255.255.0.0/16", "add")],
        [("255.0.0.0", "255.255.255.0"),],
        clear=False
    )
    test_sre(
        [("255.255.248.0/21", "add")],
        [("255.0.0.0", "255.255.255.0")],
        clear=False
    )
    test_sre(
        [("255.0.0.0/8", "del")],
        [("255.255.0.0", "255.255.255.0")],
        clear=False
    )

    # --------------------------------------------------------
    new_usres(4, 24)
    test_sre(
        [("255.0.0.0/8", "add")],
        [("255.0.0.0", "255.255.255.0")]
    )
    test_sre(
        [("255.255.0.0/16", "add")],
        [("255.0.0.0", "255.255.255.0"),],
        clear=False
    )
    test_sre(
        [("255.255.248.0/21", "add")],
        [("255.0.0.0", "255.255.255.0")],
        clear=False
    )
    test_sre(
        [("240.0.0.0/4", "add")],
        [("240.0.0.0", "255.255.255.0")],
        clear=False
    )
    test_sre(
        [("255.0.0.0/8", "del")],
        [("240.0.0.0", "255.255.255.0")],
        clear=False
    )
    test_sre(
        [("240.0.0.0/4", "del")],
        [("255.255.0.0", "255.255.255.0")],
        clear=False
    )

    # --------------------------------------------------------
    new_usres(4, 24)
    test_sre(
        [("10.1.0.0/24", "add")],
        [("10.1.0.0", "10.1.0.0")]
    )
    test_sre(
        [("10.1.1.0/24", "add")],
        [("10.1.0.0", "10.1.0.0"),
         ("10.1.1.0", "10.1.1.0")],
        clear=False
    )
    test_sre(
        [("10.1.0.0/23", "add")],
        [("10.1.0.0", "10.1.1.0")],
        clear=False
    )

    # --------------------------------------------------------
    new_usres(4, 24)
    test_sre(
        [("10.1.0.0/24", "add"),
         ("10.1.1.0/24", "add"),
         ("10.1.2.0/24", "add"),
         ("10.1.3.0/24", "add")],
        [("10.1.0.0", "10.1.0.0"),
         ("10.1.1.0", "10.1.1.0"),
         ("10.1.2.0", "10.1.2.0"),
         ("10.1.3.0", "10.1.3.0")]
    )
    test_sre(
        [("10.1.0.0/23", "add")],
        [("10.1.2.0", "10.1.2.0"),
         ("10.1.3.0", "10.1.3.0"),
         ("10.1.0.0", "10.1.1.0")],
        clear=False
    )
    test_sre(
        [("10.1.0.0/22", "add")],
        [("10.1.0.0", "10.1.3.0")],
        clear=False
    )

    # --------------------------------------------------------
    new_usres(4, 24)
    test_sre(
        [("0.0.0.0/8", "add")],
        [("0.0.0.0", "0.255.255.0")]
    )
    add_list = [("{}.0.0.0/8".format(i+1), "add")
                for i in range(255)]
    test_sre(
        add_list,
        [("{}.0.0.0".format(i), "{}.255.255.0".format(i))
         for i in range(256)],
        clear=False,
        action_descr="adding {} -> {}...".format(
            add_list[0][0], add_list[-1][0]
        ),
        print_details=False
    )
    test_sre(
        [("0.0.0.0/1", "add")],
        [("{}.0.0.0".format(128+i), "{}.255.255.0".format(128+i))
         for i in range(128)] +
         [("0.0.0.0", "127.255.255.0")],
        clear=False,
        action_descr="adding 0.0.0.0/1...",
        print_details=False
    )
    test_sre(
        [("128.0.0.0/1", "add")],
        [("0.0.0.0", "127.255.255.0"),
         ("128.0.0.0", "255.255.255.0")],
        clear=False
    )

    # --------------------------------------------------------
    new_usres(6, 64)
    test_sre(
        [
            ("1:2:3::/48", "add"),
            ("1:2:4::/48", "add")
        ],
        [
            ("1:2:3::", "1:2:3:ffff::"),
            ("1:2:4::", "1:2:4:ffff::")
        ],
        print_details=False
    )
    test_sre(
        [("1::/16", "add")],
        [("1::", "1:ffff:ffff:ffff::")],
        clear=False,
        print_details=False
    )
    test_sre(
        [("1:2:5::/48", "add")],
        [("1::", "1:ffff:ffff:ffff::")],
        clear=False,
        print_details=False
    )

def test_load():
    run_random_load_tests = True
    #run_random_load_tests = False
    if run_random_load_tests:
        target_prefix_len = 24
        test_random_load(4, 100, target_prefix_len)
        test_random_load(4, 1000, target_prefix_len)
        test_random_load(4, 10000, target_prefix_len)
        test_random_load(4, 30000, target_prefix_len)
        test_random_load(4, 100000, target_prefix_len)
        test_random_load(4, 500000, target_prefix_len)

        target_prefix_len = 64
        test_random_load(6, 100, target_prefix_len)
        test_random_load(6, 1000, target_prefix_len)
        test_random_load(6, 10000, target_prefix_len)

global sqlite_lib
for sqlite_lib in ("sqlite3", "apsw"):
    new_usres(4, 24)
    print("Testing with {} library and SQLite version {}".format(
        usres_monitor.sqlite_lib_name,
        usres_monitor.sqlite_version
    ))
    print("")

    test_base()
    test_sres()
    test_load()

    print("\n\n")

usres_monitor.dump_all()
