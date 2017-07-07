Unique Smallest Routable Entries Monitor (USREsMonitor)
=======================================================

|Build Status| |PYPI Version|

This library is inspired by an issue opened by Thomas Mangin on the repository of [InvalidRoutesReporter](https://github.com/pierky/invalidroutesreporter): https://github.com/pierky/invalidroutesreporter/issues/1

Given a set (or stream) of IP prefixes, this library calculates the unique smallest routable entries (SREs) covered by them.

De-duplication of overlapping prefixes is performed. SREs are calculated on the basis of a target prefix length that can be set on input.

Prefixes can be added and removed as they come (for example from a BGP session) and the resultant set of unique SREs is computed accordingly.

Example:

```
>>> from pierky.usres_monitor import UniqueSmallestRoutableEntriesMonitor
>>> monitor = UniqueSmallestRoutableEntriesMonitor(target_prefix_len4=24)
>>> monitor.add_net("192.168.0.0/16")
>>> ["first: {first_ip}, last: {last_ip}, cnt: {cnt}".format(**prefix) for prefix in monitor.get_prefixes(4)]
['first: 192.168.0.0, last: 192.168.255.0, cnt: 256']
>>> monitor.get_count(4)
256
```

So, 192.168.0.0/16 contains 256 /24 subnets.

Now, add a prefix that is already covered by the previous one:

```
>>> monitor.add_net("192.168.0.0/21")
>>> ["first: {first_ip}, last: {last_ip}, cnt: {cnt}".format(**prefix) for prefix in monitor.get_prefixes(4)]
['first: 192.168.0.0, last: 192.168.255.0, cnt: 256']
```

Nothing changed. Add a prefix that covers the 2 already added before:

```
>>> monitor.add_net("192.0.0.0/8")
>>> ["first: {first_ip}, last: {last_ip}, cnt: {cnt}".format(**prefix) for prefix in monitor.get_prefixes(4)]
['first: 192.0.0.0, last: 192.255.255.0, cnt: 65536']
```

Here it is, 192.0.0.0/8 covers both 192.168.0.0/16 and 192.168.0.0/21 and contains 65536 /24 subnets.

Now remove the two larger prefixes:

```
>>> monitor.del_net("192.0.0.0/8")
>>> monitor.del_net("192.168.0.0/16")
>>> ["first: {first_ip}, last: {last_ip}, cnt: {cnt}".format(**prefix) for prefix in monitor.get_prefixes(4)]
['first: 192.168.0.0, last: 192.168.7.0, cnt: 8']
```

Only 192.168.0.0/21 remains, with its 8 /24 subnets.

Add now a second prefix:

```
>>> monitor.add_net("192.168.8.0/21")
>>> ["first: {first_ip}, last: {last_ip}, cnt: {cnt}".format(**prefix) for prefix in monitor.get_prefixes(4)]
['first: 192.168.0.0, last: 192.168.7.0, cnt: 8', 'first: 192.168.8.0, last: 192.168.15.0, cnt: 8']
>>> monitor.get_count(4)
16
```

Two prefixes are printed, each one covering 8 SREs, for a total of 16 SREs.

Both IPv4 and IPv6 can be used, also simultaneously with the same monitor object:

```
>>> from pierky.usres_monitor import UniqueSmallestRoutableEntriesMonitor
>>> monitor = UniqueSmallestRoutableEntriesMonitor(target_prefix_len4=24, target_prefix_len6=56)
>>> monitor.add_net("192.168.0.0/16")
>>> monitor.add_net("10.0.0.0/8")
>>> monitor.add_net("2001:db8:aaaa::/48")
>>> ["first: {first_ip}, last: {last_ip}, cnt: {cnt}".format(**prefix) for prefix in monitor.get_prefixes(4)]
['first: 192.168.0.0, last: 192.168.255.0, cnt: 256', 'first: 10.0.0.0, last: 10.255.255.0, cnt: 65536']
>>> ["first: {first_ip}, last: {last_ip}, cnt: {cnt}".format(**prefix) for prefix in monitor.get_prefixes(6)]
['first: 2001:db8:aaaa::, last: 2001:db8:aaaa:ff00::, cnt: 256']
>>> monitor.get_count(4)
65792
>>> monitor.get_count(6)
256
```

Installation
------------

```
pip install usresmonitor
```

Optionally, the [apsw](https://github.com/rogerbinns/apsw) SQLite library can be installed; in that case, it will be preferred during the setup of the backend database used by USREsMonitor.

Future work
-----------

Add some examples of how this library can be used (ExaBGP integration).

Status
------

**First-release**, looking for testers and reviewers.

Bug? Issues?
------------

But also suggestions? New ideas?

Please create an `issue on GitHub <https://github.com/pierky/usres_monitor/issues>`_ or `drop me a message <https://pierky.com/#contactme>`_.

Author
------

Pier Carlo Chiodi - https://pierky.com

Blog: https://blog.pierky.com Twitter: `@pierky <https://twitter.com/pierky>`_

.. |Build Status| image:: https://travis-ci.org/pierky/usres_monitor.svg?branch=master
    :target: https://travis-ci.org/pierky/usres_monitor
.. |PYPI Version| image:: https://img.shields.io/pypi/v/usres_monitor.svg
    :target: https://pypi.python.org/pypi/usres_monitor/
