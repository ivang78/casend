## Description

This small utility is designed for file transfer with Casio PB-100/110, FX-700P/730P, Tandy PC-4, and similar pocket computers.
It uses the FA-3 cassette interface emulator developed by [Piotr Piatek](https://pisi.com.pl/piotr433/tape.htm).
The original design assumed the use of terminal applications such as Tera Term, PuTTY, or Minicom. However, the interface relies on software flow control (XON/XOFF) to prevent buffer overruns. Under Linux, terminal applications typically rely on the serial driver to implement XON/XOFF. Many USB-to-serial drivers do not support XON/XOFF and therefore do not pause data transmission when XON/XOFF control characters are received.
This utility therefore implements XON/XOFF flow control in software.

## Installation
You have to install python3, pip and pyserial library before usage

## Usage

The USB-to-serial device is detected automatically at startup by scanning ttyUSBx and ttyACMx devices. 
You can also specify the serial port manually using the --port command-line argument.

### Interactive mode

**python3 casend.py** - run interactively in autodetect mode
**python3 casend.py -- port /dev/ttyUSB0** - runs interactively with specified serial port*

### Command line mode

**python3 casend.py send examples/RIVER.ASC** - send file examples/RIVER.ASC to pocket computer in autodetect mode
**python3 casend.py receive examples/RIVER.ASC** - receive file to examples/RIVER.ASC to pocket computer in autodetect mode

## Example
