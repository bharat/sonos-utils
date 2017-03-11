#!/usr/bin/python
import os
import sys

import argparse
import commands
import multiprocessing
import numpy
import re
import soco
import socket
import time
import urllib2
import xml.etree.ElementTree as ElementTree


def zp_request(zp_ip, request):
    url = 'http://%s:1400/%s' % (zp_ip, request)
    return urllib2.urlopen(url, timeout=5).read()


def name(ip):
    try:
        return socket.gethostbyaddr(ip)[0].split('.')[0]
    except:
        return ip


def fuzz(mac):
    """
    Return a table with the mac address as well as 6 variants. The variants
    are the addresses where each of the last 3 components is offset +/- 1
    address.
    """
    components = [int(x, 16) for x in mac.split(':')]
    offsets = [
        [0, 0, 0,  0,  0, -1], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 1],
        [0, 0, 0,  0, -1,  0],                     [0, 0, 0, 0, 1, 0],
        [0, 0, 0, -1,  0,  0],                     [0, 0, 0, 1, 0, 0]
    ]

    table = []
    for variant in offsets:
        table.append(':'.join(['{:02X}'.format(sum(x) % 256)
                               for x in zip(components, variant)]))
    return table


def build_fuzzy_rev_arp():
    """
    Build a reverse arp table to map MAC addresses to host names.

    Many access points have two NICs so the MAC address that the Sonos
    sees may not be the one that shows up in the arp table. Fuzz each
    MAC addr enough so that we have a high likelihood of matching.
    """
    rev_arp_table = {}
    if os.path.exists('/proc/net/arp'):
        for line in open('/proc/net/arp').read().splitlines():
            fields = line.split()
            if ':' in fields[3]:
                for fuzzy_mac in fuzz(fields[3].upper()):
                    rev_arp_table[fuzzy_mac] = name(fields[0])
    return rev_arp_table


def get_network_data(zp_ip):
    rev_arp = build_fuzzy_rev_arp()

    data = {}
    data['beacons'] = ''
    data['drops'] = ''
    data['prr'] = ''
    data['chsnk_score'] = ''
    data['rssi'] = ''
    data['tx'] = ''

    try:
        response = zp_request(zp_ip, 'status/proc/ath_rincon/station')
        if 'SSID' in response:
            data['ssid'] = list(re.findall(
                r'SSID: \[(.*)\] \((\d+)\) ([0-9A-F:]{17})', response)[0])
            data['channel'] = list(re.findall(
                r'Channel: current: (\d+) ap: (\d+)', response)[0])[1]

            wap_hostname = data['ssid'][2]
            if wap_hostname in rev_arp:
                wap_hostname = rev_arp[wap_hostname]
            data['network'] = wap_hostname

            # Parse the last line of the network receive stats
            tree = ElementTree.fromstring(response)
            cols = re.split('\s+', tree[0].text.split("\n")[-3])
            data['beacons'] = cols[5]
            data['drops'] = cols[-3]
            data['prr'] = cols[-4]
        else:
            data['network'] = 'Wired'
            data['channel'] = ''
    except urllib2.URLError as e:
        # Network errors result in '?' values which should be red flag enough
        pass

    try:
        for line in zp_request(zp_ip, 'status/dmesg').split('\n'):
            match = re.match('.* sta RSSI avg=(\d+), TX rate now (\w+).*', line)
            if match:
                (data['rssi'], data['tx']) = match.group(1, 2)
                break
    except urllib2.URLError as e:
        # Network errors result in '?' values which should be red flag enough
        pass

    try:
        response = zp_request(zp_ip, 'status/perf')
        tree = ElementTree.fromstring(response)
        chsnk = tree.find('./PerformanceCounters/Counter[@name="CHSNK Fill Level"]')

        chsnk_ints = [int(x) for x in chsnk.text.split('\n')[2].split()[1:]][0:11]
        chsnk_sum = numpy.sum(chsnk_ints)
        if chsnk_sum:
            chsnk_score = numpy.dot(chsnk_ints, range(1, 12)) / float(chsnk_sum*11)
            data['chsnk_score'] = '%6.3f' % chsnk_score
    except urllib2.URLError as e:
        # Network errors result in '?' values which should be red flag enough
        pass

    return data


def get_wifi_scan(zp_ip):
    data = []
    try:
        response = zp_request(zp_ip, 'status/scanresults')
        tree = ElementTree.fromstring(response)
        for line in tree.find('./Command').text.split('\n'):
            if ': chan:' in line:
                data.append(line)

    except urllib2.URLError as e:
        # Network errors result in '?' values which should be red flag enough
        pass

    return data


def get_wifi_blacklist(zp_ip):
    data = []
    try:
        response = zp_request(zp_ip, 'status/dmesg')
        tree = ElementTree.fromstring(response)
        for line in tree.find('./Command').text.split('\n'):
            if 'blacklisted' in line:
                data.append(line)

    except urllib2.URLError as e:
        # Network errors result in '?' values which should be red flag enough
        pass

    return data


def zp_name(zp):
    return zp.get_speaker_info()['zone_name']


def zp_print(zp, fmt, net_data, level):
    padding = level * '  '

    state = ''
    if zp.is_visible and level == 0:
        state = zp.get_current_transport_info()['current_transport_state']

    print fmt % (
        padding + zp_name(zp),
        '%s (%s)' % (net_data[zp]['network'], net_data[zp]['channel']),
        state,
        net_data[zp]['rssi'],
        net_data[zp]['beacons'],
        net_data[zp]['drops'],
        net_data[zp]['chsnk_score'])

    if level == 0:
        for grouped_zp in sorted(zp.group, key=lambda x: zp_name(x)):
            if grouped_zp is not zp:
                zp_print(grouped_zp, fmt, net_data, level + 1)


def all_zps_sorted():
    zps = soco.discover(
        include_invisible=True,
        interface_addr=socket.gethostbyname(socket.gethostname()))
    if zps:
        zps = sorted(zps, key=lambda x: zp_name(x))
    return zps


def map_network(zps, args):
    fmt = '%-18.18s %25.25s %-18.18s  %5.5s %5.5s %5.5s %6.6s'

    # Gather up all net data in parallel. We can't pass ZonePlayer objects
    # across the process boundary so deal in IPs
    net_data = {}
    p = multiprocessing.Pool(len(zps))
    zp_ips = [x.ip_address for x in zps]
    for (zp, nd) in zip(zps, p.map(get_network_data, zp_ips)):
        net_data[zp] = nd

    print fmt % ('Sonos', 'Network', 'State', 'RSSI', 'B#', 'Drops', 'CHSNK')
    for zp in zps:
        if zp.is_coordinator:
            zp_print(zp, fmt, net_data, 0)


def wifi_status(zps, args):
    rev_arp = build_fuzzy_rev_arp()

    # Gather up all scan data in parallel. We can't pass ZonePlayer objects
    # across the process boundary so deal in IPs
    scan_data = {}
    p = multiprocessing.Pool(len(zps))
    zp_ips = [x.ip_address for x in zps]
    for (zp, result) in zip(zps, p.map(get_wifi_scan, zp_ips)):
        scan_data[zp] = result

    net_data = {}
    p = multiprocessing.Pool(len(zps))
    zp_ips = [x.ip_address for x in zps]
    for (zp, nd) in zip(zps, p.map(get_network_data, zp_ips)):
        net_data[zp] = nd

    for zp in zps:
        current_ap = net_data[zp]['network']
        print 'Sonos: %s (connected to %s)' % (zp_name(zp), current_ap)
        sorted_by_rssi = sorted(
            [x for x in scan_data[zp] if 'rssi: ' in x],
            key=lambda l: int(re.search('rssi:\s*(\d+)', l).group(1)),
            reverse=True)
        if sorted_by_rssi:
            filtered = [x for x in sorted_by_rssi if args.filter in x]
            renamed = []

            if filtered:
                for line in filtered:
                    for (mac, name) in rev_arp.iteritems():
                        mac = mac.lower()   # scan results have lower case MAC
                        line = line.replace(mac, '%20.20s' % name)
                    renamed.append(line)
                print '\n'.join(renamed)

                best_ap = re.search('(\S+): ', renamed[0]).group(1)
                if current_ap != best_ap:
                    print '******** NOT OPTIMAL: change access point from [%s] to [%s]' % (
                        current_ap, best_ap)

        print '\n'


def wifi_blacklist(zps, args):
    rev_arp = build_fuzzy_rev_arp()

    # Gather up all scan data in parallel. We can't pass ZonePlayer objects
    # across the process boundary so deal in IPs
    scan_data = {}
    p = multiprocessing.Pool(len(zps))
    zp_ips = [x.ip_address for x in zps]
    for (zp, result) in zip(zps, p.map(get_wifi_blacklist, zp_ips)):
        scan_data[zp] = result

    for zp in zps:
        print 'Sonos: %s' % zp_name(zp)
        for line in scan_data[zp]:
            for (mac, name) in rev_arp.iteritems():
                mac = mac.lower()   # dmesg results have mac in lower case
                line = line.replace(mac, '%20.20s' % name)
            print line
        print


def reboot_network(zps, args):
    print "REBOOTING THESE SONOS IN 5 SECONDS!\n\t%s\nHit ^C to abort" % \
        "\n\t".join([zp_name(x) for x in zps])
    time.sleep(5)

    for zp in zps:
        try:
            response = zp_request(zp.ip_address, 'reboot')
            print response
        except urllib2.URLError as e:
            print e


def main(argv=None):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='cmd')
    parser_map = subparsers.add_parser('map')
    parser_reboot = subparsers.add_parser('reboot')
    parser_wifi_status = subparsers.add_parser('wifi-status')
    parser_wifi_status.add_argument('--filter', metavar='filter', nargs='?', default='', help='Wifi SSID filter')
    parser_wifi_blacklist = subparsers.add_parser('wifi-blacklist')

    args = parser.parse_args()

    zps = all_zps_sorted()
    if not zps:
        print 'No Sonos devices detected'
        sys.exit(1)

    cmd_exec = {
        'map': map_network,
        'wifi-status': wifi_status,
        'wifi-blacklist': wifi_blacklist,
        'reboot': reboot_network,
        }
    cmd_exec[args.cmd](zps, args)


if __name__ == '__main__':
    main(sys.argv)



