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

class USRESMonitorException(Exception):
    pass


class UniqueSmallestRoutableEntriesMonitor(object):

    def load_sqlite(self, force_sqlite_lib=None):
        """Load sqlite3/apsw library

        If no hints are given, it tries the apsw library then sqlite3.
        """

        if force_sqlite_lib and force_sqlite_lib not in("sqlite3", "apsw"):
            raise USRESMonitorException(
                "Unknown SQLite library: {}. Must be sqlite3 or apsw".format(
                    force_sqlite_lib
                )
            )

        def load_sqlite3():
            import sqlite3 as sqlite_lib
            self.sqlite_lib = sqlite_lib
            self.sqlite_lib_name = "sqlite3"
            self.sqlite_version = sqlite_lib.sqlite_version

        def load_apsw():
            import apsw as sqlite_lib
            self.sqlite_lib = sqlite_lib
            self.sqlite_lib_name = "apsw"
            self.sqlite_version = sqlite_lib.sqlitelibversion()

        if force_sqlite_lib == "sqlite3":
            load_sqlite3()
        elif force_sqlite_lib == "apsw":
            load_apsw()
        else:
            try:
                load_apsw()
            except:
                load_sqlite3()

    def __init__(self, target_prefix_len4=24, target_prefix_len6=40,
                 force_sqlite_lib=None):
        """Init a USREs monitor for prefixes of given length"""

        assert target_prefix_len4 > 0, "Invalid IPv4 target prefix length"
        assert target_prefix_len6 > 0, "Invalid IPv6 target prefix length"
        assert target_prefix_len4 <= 32, "Max IPv4 target prefix length is 32"
        assert target_prefix_len6 <= 64, "Max IPv6 target prefix length is 64"

        self.target_prefix_len4 = target_prefix_len4
        self.target_prefix_len6 = target_prefix_len6

        self.load_sqlite(force_sqlite_lib=force_sqlite_lib)

        self.setup_db()

    def sql_out(self, sql, args=()):
        return self.cur.execute(sql, args)

    def setup_db(self):
        try:
            # sqlite3
            con = self.sqlite_lib.connect(":memory:")
        except:
            # apsw
            con = self.sqlite_lib.Connection(":memory:")

        self.cur = con.cursor()

        for ip_ver in [4, 6]:
            sql = ("CREATE TABLE"
                "    prefixes{ip_ver} ("
                "        id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "        first INTEGER,"
                "        pref_len INTEGER,"
                "        last INTEGER,"
                "        cnt INTEGER"
                "    )".format(ip_ver=ip_ver))
            self.sql_out(sql)

            sql = ("CREATE UNIQUE INDEX"
                "    prefixes{ip_ver}_pk ON"
                "    prefixes{ip_ver} ("
                "        first,"
                "        pref_len"
                "    )".format(ip_ver=ip_ver))
            self.sql_out(sql)

            sql = ("CREATE TABLE"
                "    smallest_routable_entries{ip_ver} ("
                "        id INTEGER,"
                "        first INTEGER,"
                "        pref_len INTEGER,"
                "        last INTEGER,"
                "        cnt INTEGER"
                "    )".format(ip_ver=ip_ver))
            self.sql_out(sql)

            sql = ("CREATE UNIQUE INDEX"
                "    smallest_routable_entries{ip_ver}_ok ON"
                "    smallest_routable_entries{ip_ver} ("
                "        first,"
                "        last"
                "    )".format(ip_ver=ip_ver))
            self.sql_out(sql)

            sql = ("CREATE VIEW"
                "    smallest_routable_entries{ip_ver}_view AS"
                "    SELECT"
                "        *"
                "    FROM"
                "        smallest_routable_entries{ip_ver}"
                "".format(ip_ver=ip_ver))
            self.sql_out(sql)

            sql = ("CREATE TRIGGER"
                "    smallest_routable_entries{ip_ver}_view_insert "
                "INSTEAD OF INSERT ON"
                "    smallest_routable_entries{ip_ver}_view "
                "BEGIN"
                "    INSERT INTO smallest_routable_entries{ip_ver}"
                "    SELECT NEW.id, NEW.first, NEW.pref_len, NEW.last, NEW.cnt"
                "    WHERE"
                "        NOT EXISTS ("
                "            SELECT id FROM smallest_routable_entries{ip_ver}"
                "            WHERE NEW.first BETWEEN first AND last"
                "        );"
                "END".format(ip_ver=ip_ver))
            self.sql_out(sql)

    def dump_all(self, additional_info=None):
        import time
        from random import randint
        target_file = "dump-{time}_{random}.db".format(
            time=time.strftime("%Y-%m-%d_%H%M%S"),
            random="_{:04d}".format(randint(0, 9999))
        )

        self.sql_out("ATTACH '{}' AS target".format(target_file))

        tables = ["smallest_routable_entries4", "smallest_routable_entries6",
                  "prefixes4", "prefixes6"]
        for tbl_name in tables:
            self.sql_out("CREATE TABLE target.{tbl_name} AS "
                    "SELECT * FROM main.{tbl_name}".format(
                        tbl_name=tbl_name)
            )

        if additional_info:
            with open("{}.info".format(target_file), "w") as f:
                f.write(additional_info)
        return target_file

    @staticmethod
    def get_net(net):
        if isinstance(net, (ipaddr.IPv4Network, ipaddr.IPv6Network)):
            return net
        return ipaddr.IPNetwork(net)

    @staticmethod
    def get_first(net):
        assert isinstance(net, (ipaddr.IPv4Network, ipaddr.IPv6Network))
        if net.version == 6:
            return int(net.network) >> 64
        else:
            return int(net.network)

    @staticmethod
    def get_sre(net, target_prefix_len):
        """Calculate first and last /target_prefix_len subnets from net

        Returns: first, last, cnt (all integers)
        """

        assert isinstance(net, (ipaddr.IPv4Network, ipaddr.IPv6Network))
        assert target_prefix_len <= 64, "Max target prefix length is 64"
        assert net.prefixlen <= target_prefix_len, \
            ("Prefix length ({}) must be <= of the target prefix "
             "length ({}): {}".format(net.prefixlen, target_prefix_len, net))

        first = UniqueSmallestRoutableEntriesMonitor.get_first(net)

        tot_len = 64 if net.version == 6 else 32

        # first <= 2^63 -1 to avoid overflows
        assert first <= 9223372036854775807, \
            "Only prefixes <= 7fff:ffff:ffff:ffff::/64 can be processed"

        diff_len = target_prefix_len - net.prefixlen

        last = first | ((2**diff_len - 1) << tot_len - target_prefix_len)

        return first, last, 2**diff_len

    @staticmethod
    def get_ip_repr(ip_ver, net_int):
        return ipaddr.IPAddress(net_int if ip_ver == 4 else net_int << 64)

    def add_net(self, net_or_str):
        """Add the ipaddr.IPv[4|6]Network object to db
        
        Args:
            net: ipaddr.IPv[4|6]Network object or string
        """

        net = self.get_net(net_or_str)

        target_prefix_len = self.target_prefix_len4 if net.version == 4 \
                            else self.target_prefix_len6
        first, last, cnt = self.get_sre(net, target_prefix_len)

        try:
            self.sql_out("INSERT INTO "
                         "   prefixes{} ("
                         "       first, pref_len, last, cnt"
                         "   ) "
                         "VALUES "
                         "   (?, ?, ?, ?)".format(net.version),
                         (first, net.prefixlen, last, cnt)
            )
        except Exception as e:
            if "UNIQUE constraint failed" in str(e) or \
                "columns first, pref_len are not unique" in str(e):

                raise USRESMonitorException(
                    "Processing {} but it was already in the db".format(net)
                )
            self.dump_all(
                "add_net {}\n"
                "target_prefix_len: {}\n"
                "first: {}\n"
                "last: {}\n"
                "cnt: {}\n"
                "{}".format(
                    net, target_prefix_len, first, last, cnt, str(e)
                )
            )
            raise

    def del_net(self, net_or_str):
        """Remove the ipaddr.IPv[4|6]Network object from db

        Args:
            net: ipaddr.IPv[4|6]Network object or string
        """

        net = self.get_net(net_or_str)

        first = self.get_first(net)

        try:
            self.sql_out("DELETE FROM "
                         "   prefixes{} "
                         "WHERE"
                         "   first = ? AND"
                         "   pref_len = ?".format(net.version),
                         (first, net.prefixlen)
            )
        except Exception as e:
            self.dump_all(
                "del_net {}\n"
                "first: {}\n"
                "{}".format(
                    net, first, str(e)
                )
            )
            raise

    def _populate_smallest_routable_entries(self, ip_ver):
        # MIN(first) for each last.
        sql = ("SELECT "
               "     a.* "
               "FROM "
               "     prefixes{ip_ver} a"
               "        INNER JOIN ("
               "            SELECT"
               "                last,"
               "                MIN(first) AS first"
               "            FROM"
               "                prefixes{ip_ver}"
               "            GROUP BY last"
               "        ) b ON"
               "            a.first = b.first AND"
               "            a.last = b.last"
               "".format(ip_ver=ip_ver))

        # MAX(last) for each first of previous sub-query.
        sql = ("SELECT "
               "    c.* "
               "FROM "
               "    prefixes{ip_ver} c"
               "        INNER JOIN ("
               "            SELECT "
               "                first, MAX(last) AS last "
               "            FROM "
               "                ({sql})"
               "            GROUP BY"
               "                first"
               "        ) d ON"
               "            c.first = d.first AND"
               "            c.last = d.last "
               "".format(
                   ip_ver=ip_ver,
                   sql=sql
               ))

        # Uses data from the previous sub-query.
        # Insert into the view on pref_len order (ASC); the trigger avoids
        # to add prefixes that are already coveredy by other prefixes
        # already present in the table.
        sql = ("DELETE FROM smallest_routable_entries{ip_ver}; "
               "INSERT INTO smallest_routable_entries{ip_ver}_view "
               "    SELECT * FROM ({sql}) ORDER BY pref_len; ".format(
                   ip_ver=ip_ver, sql=sql
              ))

        try:
            if self.sqlite_lib_name == "apsw":
                self.sql_out(sql)
            else:
                self.cur.executescript(sql)
        except Exception as e:
            self.dump_all(
                "_populate_smallest_routable_entries {}\n"
                "{}".format(
                    ip_ver, str(e)
                )
            )
            raise

    def get_prefixes(self, ip_ver):
        """Get the list of not overlapping prefixes and their SREs

        This is a generator of dict in this format:

        {
            "id": internal ID of the prefix.

            "first_int": the integer representation of the first subnet
                covered by the prefix, calculated on the basis of the
                target prefix length given as input.
                For IPv4 prefixes, this is the real network ID of the
                prefix; for IPv6 addresses, this is the highest 64-bit value
                of the network ID.

            "first_ip": a string that represents the IP notation of the
                first network covered by this prefix.

            "pref_len": the length of the prefix that generated the entry.

            "last_int": the integer representation of the last subnet
                covered by the prefix, calculated on the basis of the
                target prefix length given as input.
                What said for "first_int" also applies to "last_int".

            "last_ip": a string that represents the IP notation of the
                last network covered by this prefix.

            "cnt": number of SREs covered by this prefix.
             
        }
        """

        self._populate_smallest_routable_entries(ip_ver)

        sql = ("SELECT "
               "    id, first, pref_len, last, cnt "
               "FROM "
               "    smallest_routable_entries{ip_ver} "
               "ORDER BY "
               "    id".format(ip_ver=ip_ver))

        rs = self.sql_out(sql)
        record = rs.fetchone()
        while record:
            res = {
                "id": record[0],
                "first_int": record[1],
                "first_ip": str(self.get_ip_repr(ip_ver, record[1])),
                "pref_len": record[2],
                "last_int": record[3],
                "last_ip": str(self.get_ip_repr(ip_ver, record[3])),
                "cnt": record[4]
            }
            yield res
            record = rs.fetchone()

    def get_count(self, ip_ver):
        """Get the total number of SREs covered by not overlapping prefixes

        Return: int
        """

        self._populate_smallest_routable_entries(ip_ver)

        sql = ("SELECT "
               "    SUM(cnt) "
               "FROM "
               "    smallest_routable_entries{ip_ver} "
               "ORDER BY "
               "    id".format(ip_ver=ip_ver))
        return self.sql_out(sql).fetchall()[0][0]
