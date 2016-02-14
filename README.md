# sonos-utils
Management and diagnostic tools for a Sonos network.

I've got a complex network and large number of Sonos devices. I was
experiencing grouping issues and drop-outs so I wrote a tool that
reads the diagnostic data from each Sonos and aggregates it.

## Requirements
You'll need to install the `soco` module which does Sonos discovery.

  ``pip install soco``

## Mapping and diagnostics

``sonos map`` will discover Sonos devices on your network and display
them in a hierarchical form. Here's some sample output:

```
Sonos              Network                   State                RSSI    B# Drops  CHSNK
Family Room        wap-family-room (6)       PLAYING                86   498    96  1.000
 Dining Room       wap-family-room (6)       PLAYING                55   584    24  1.000
 Master Bathroom   wap-master-bedroom (11)   PLAYING                41   550    37  1.000 
 Master Bedroom    wap-master-bedroom (11)   PLAYING                     524    25  1.000  
Living Room        wap-living-room (1)       STOPPED                42   197    36   
WEMY WOOM!         wap-bedroom-2 (11)        PLAYING                     585    33  0.752   
 Office            wap-office (1)            PLAYING                     241    11  1.000   
 Piano Room        Wired                     PLAYING                72              1.000    
 Upstairs          wap-bedroom-2 (11)        PLAYING                     585    41  1.000     
```

### How to read this data: 

Sonos: the name of the sonos. Rows are grouped by group leader, so note that `Dining Room` is grouped under `Family Room`. You may see `Dining Room` report as `PLAYING` when it's attached, even if the group leader is not playing anything - but it's doing whatever the group leader does at that point. I should probably clean that up a bit.

Network: the name of the wireless access point the Sonos is connected to. This is useful in the case where you have multiple access points in your system. The number in parentheses is the wireless channel. We use ARP to figure out the IP of the access point, and DNS to resolve it to a name. If you don't have one or the other of those set up, you may see a MAC address or an IP address in this column. If the device is not using wifi, then it'll report as `Wird` (see `Piano Room` above).

State: `PLAYING`, `STOPPED` or `PAUSED_PLAYBACK` in the case where the Sonos is paused in the middle of a song.

RSSI: The wifi signal strength. Higher number is better. This is scraped out of the Sonos dmesg log which expires old message, so it's possible that the data is missing if the Sonos hasn't changed it's access point in a while or has been up for a long time.

B#: The number of wifi beacons that made it through to this Sonos in the last 60 seconds. Beacons happen every 100ms or 10 a second reported in 60 second intervals. A number above 400 is ok, above 500 is good.

Drops: The number of dropped packets in the last 60 seconds

CHSNK: This is the one to watch. It's a score based on how much data is getting buffered by each individual Sonos. On a system where all the Sonos are working properly, you should see all of these approach `1.000`, but if you add a new Sonos to a group or one of your Sonos does not have a good signal, you'll see a low fraction here. This is the closest thing I've found to identifying whether a Sonos is emitting music or not. If you see a consistently low level here then it means that the Sonos is not buffering music fast enough to keep up with the stream. You might see a low level when you start playing a stream (see `WEMY WOOM!` above) but if it's trending up consistently that's likely because it's just catching up.

## Utility functions

``sonos reboot`` will restart every Sonos on your system. I found this convenient when I was doing lots of system-level changes.


