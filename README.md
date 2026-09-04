# MCan viewer

This repository contains the source code for the MCan viewer, which is mainly
used to display CAN packets received from MCan in real time. This program
can also be used to program boards via MCan.

This program can be used in two ways: in a script or as a standalone program.
To use the standalone program, connect the MCan devide to your computer and
run `mcan_test.py`. Scripting allows you to customize the way in which data is
displayed and integrate the MCan viewer with other programs.

## Installation
To install the MCan viewer, clone the repository:
```
git clone https://github.com/RITRacingSoftware/MCAN.git
cd MCAN
```
It is recommended that you create a virtual environment for this project:
```
python3 -m virtualenv venv
source venv/bin/activate
```
Next, install MCAN with
```
pip install .
```

You can run MCan with `python3 mcan_test.py`. MCan will listen for packets from
the MCan board and decode them according to their DBCs.

## Connecting the MCan board to your computer
MCan communicates with your computer over 10Base-T Ethernet. For MCan to
connect, automatic link negotiation must be disabled and the speed must be
fixed at 10 Mb/s. If possible, the connection should be configured to be
half-duplex. MCan has a static IP of 192.168.72.100, and your computer's IP
should be set to 192.168.72.1 with DHCP disabled. IPv6 should be disabled.
You can determine if MCan has connected successfully by pinging its IP address.

MCan receives and transmits CAN data over UDP. Packets transmitted by MCan
originate from port 5001. To receive data from MCan, your computer must listen
on port 40000. Packets from your computer are received on port 5001.
