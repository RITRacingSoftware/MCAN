import socket
import struct

ethernet_socket = None

def ethernet_start():
    global ethernet_socket
    ethernet_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ethernet_socket.bind(("192.168.72.1", 40000))

def ethernet_tx(packet):
    frame = bytearray([0x55, 0xff, packet["bus"], 0x80 | (len(packet["data"])+4)])+struct.pack("<I", packet["id"])+packet["data"]
    ethernet_socket.sendto(frame, ('192.168.72.100', 5001))

