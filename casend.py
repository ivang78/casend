#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exchange files with a Casio PB-100/110/FX-730 pocket computer over a USB serial adapter."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import serial
except ImportError:  # pragma: no cover - exercised only without the dependency
    serial = None  # type: ignore[assignment]


BAUDRATE = 9600
GAP_SECONDS = 2.0
PORT_COUNT = 100
POLL_SECONDS = 0.01
XON = b"\x11"
XOFF = b"\x13"


def find_serial_port(port: Optional[str] = None):
    """Open an explicitly selected port or find the first usable USB port."""
    if serial is None:
        raise RuntimeError(
            "PySerial library is not installed. Please install it by typing command: "
            "python3 -m pip install pyserial"
        )

    if port is not None:
        return serial.Serial(
            port=port,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            # XON/XOFF is handled in send_file().  Let the application
            # receive these bytes instead of leaving it to the Linux
            # serial driver (via PySerial).
            xonxoff=False,
            timeout=None,
        )

    attempted = []
    for prefix in ("ttyUSB", "ttyACM"):
        for index in range(PORT_COUNT):
            device = f"/dev/{prefix}{index}"
            if not os.path.exists(device):
                continue
            attempted.append(device)
            try:
                return serial.Serial(
                    port=device,
                    baudrate=BAUDRATE,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    # XON/XOFF is handled in send_file().  Let the application
                    # receive these bytes instead of leaving it to the Linux
                    # serial driver (via PySerial).
                    xonxoff=False,
                    timeout=None,
                )
            except (OSError, serial.SerialException):
                continue

    if attempted:
        details = " (can not open: " + ", ".join(attempted) + ")"
    else:
        details = ""
    raise RuntimeError("USB-serial port not found" + details)


def validate_send_file(filename: str) -> Optional[Path]:
    path = Path(filename).expanduser()
    if not path.is_file() or not os.access(path, os.R_OK):
        print(f"ERROR: file not found or permission error: {path}", file=sys.stderr)
        return None
    return path


def validate_receive_file(filename: str) -> Optional[Path]:
    path = Path(filename).expanduser()
    if path.exists():
        print(f"ERROR: file is already exists: {path}", file=sys.stderr)
        return None
    parent = path.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        print(f"ERROR: destination directory is inaccessible: {parent}", file=sys.stderr)
        return None
    return path


def send_file(path: Path, ser) -> None:
    """Send *path*, observing software XON/XOFF flow control explicitly."""
    paused = False

    with path.open("rb") as source:
        byte = source.read(1)
        while byte:
            if paused:
                # At the start of a transfer (and after XOFF) do not send any
                # data until the receiver explicitly grants permission.
                if ser.in_waiting <= 0:
                    time.sleep(POLL_SECONDS)
                    continue
                control = ser.read(1)
                if not control:
                    raise OSError("Serial port closed connection while waiting XON")
                if control == XON:
                    paused = False
                elif control == XOFF:
                    paused = True
                continue

            count = ser.write(byte)
            if count != len(byte):
                raise OSError("Serial port does not receive data")

            # Do not allow the operating system's output queue to get ahead of
            # the receiver: XOFF must be able to stop the very next byte.
            ser.flush()
            while ser.in_waiting:
                control = ser.read(1)
                if control == XOFF:
                    paused = True
                elif control == XON:
                    paused = False
            byte = source.read(1)


def receive_file(path: Path, ser) -> None:
    # The first byte is intentionally read without a timeout.
    while True:
        if ser.in_waiting <= 0:
            time.sleep(POLL_SECONDS)
            continue
        first = ser.read(1)
        if not first:
            raise OSError("Serial port inaccessible")
        if first not in (XON, XOFF):
            break

    with path.open("xb") as target:
        target.write(first)
        previous = time.monotonic()
        while True:
            now = time.monotonic()
            if now - previous > GAP_SECONDS:
                break
            if ser.in_waiting <= 0:
                time.sleep(POLL_SECONDS)
                continue
            current = ser.read(1)
            if current in (XON, XOFF):
                # These control bytes were previously consumed by PySerial.
                continue
            if current:
                target.write(current)
                previous = now


def run_operation(command: str, filename: str, port: Optional[str] = None) -> str:
    """Run one operation and return: success, retry_filename, or retry_mode."""
    if command == "send":
        path = validate_send_file(filename)
    else:
        path = validate_receive_file(filename)
    if path is None:
        return "retry_filename"

    try:
        ser = find_serial_port() if port is None else find_serial_port(port)
        try:
            if command == "send":
                send_file(path, ser)
            else:
                receive_file(path, ser)
        finally:
            ser.close()
    except Exception as exc:
        print(f"ERROR exchange: {exc}", file=sys.stderr)
        return "retry_mode"

    if command == "send":
        print(f"File successfully sent: {path}")
    else:
        print(f"File successfully received: {path}")
    return "success"


def choose_mode() -> str:
    """Read the mode selection without waiting for the Return key.

    The interactive program is intended for a terminal, where putting stdin
    into cbreak mode lets us read one key immediately.  A line-oriented
    fallback is kept for redirected input and for callers that provide a
    non-terminal stdin (for example, automated tests).
    """

    stdin_is_tty = sys.stdin.isatty()

    def read_choice() -> str:
        if not stdin_is_tty:
            return input().strip()

        if os.name == "nt":
            import msvcrt

            return msvcrt.getwch()

        import termios
        import tty

        fd = sys.stdin.fileno()
        settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, settings)

    while True:
        print("Change working mode by pressing keys 1 or 2::")
        print("\t1 - Send file")
        print("\t2 - Receive file")
        choice = read_choice()
        # The selected key is not followed by Return, so finish the line
        # before displaying the next prompt.
        if stdin_is_tty:
            print()
        if choice == "1":
            return "send"
        if choice == "2":
            return "receive"
        print("ERROR: press 1 or 2")


def interactive_loop(port: Optional[str] = None) -> int:
    try:
        while True:
            command = choose_mode()
            while True:
                filename = input("Введите имя файла:\n").strip()
                if not filename:
                    print("Ошибка: имя файла не может быть пустым.")
                    continue
                result = run_operation(command, filename, port)
                if result == "retry_filename":
                    continue
                break
    except (EOFError, KeyboardInterrupt):
        print()
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exchange files with a Casio PB-100/110/FX-730 pocket computer over a USB serial adapter"
    )
    parser.add_argument("command", nargs="?", choices=("send", "receive"))
    parser.add_argument("file", nargs="?", help="file name")
    parser.add_argument(
        "--port",
        help="serial port to use (skip automatic port detection)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command is None:
        return interactive_loop(args.port)

    print("Exchange files with a Casio PB-100/110/FX-730 pocket computer over a USB serial adapter");

    filename = args.file
    if filename is None:
        try:
            filename = input("Enter file name:\n").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return 1
        if not filename:
            print("ERROR: filename can not be empty", file=sys.stderr)
            return 1

    result = run_operation(args.command, filename, args.port)
    return 0 if result == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
