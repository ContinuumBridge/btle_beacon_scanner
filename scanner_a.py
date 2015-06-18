#!/usr/bin/env python
# scanner_a.py
# Copyright (C) ContinuumBridge Limited, 2015 - All Rights Reserved
# Written by Peter Claydon
#

import sys
import time
import json
from cbcommslib import CbAdaptor
from cbconfig import *
from twisted.internet import threads
from twisted.internet import reactor
import blescan
import bluetooth._bluetooth as bluez

TRY_START_INTERVAL     = 10  # How often to retry BLE scanning if it fails to start

class Adaptor(CbAdaptor):
    def __init__(self, argv):
        self.status =           "ok"
        self.state =            "stopped"
        self.uuids =            {}
        # super's __init__ must be called:
        #super(Adaptor, self).__init__(argv)
        CbAdaptor.__init__(self, argv)

    def setState(self, action):
        # error is only ever set from the running state, so set back to running if error is cleared
        if action == "error":
            self.state == "error"
        elif action == "clear_error":
            self.state = "running"
        msg = {"id": self.id,
               "status": "state",
               "state": self.state}
        self.sendManagerMessage(msg)

    def sendCharacteristic(self, characteristic, data, timeStamp):
        msg = {"id": self.id,
               "content": "characteristic",
               "characteristic": characteristic,
               "data": data,
               "timeStamp": timeStamp}
        u = data["uuid"]
        if u in self.uuids:
            for a in self.uuids[u]:
                self.sendMessage(msg, a)

    def startScan(self):
        dev_id = 0
        try:
            self.sock = bluez.hci_open_dev(dev_id)
            blescan.hci_le_set_scan_parameters(self.sock)
            blescan.hci_enable_le_scan(self.sock)
            blescan.cbLog = self.cbLog
            return True
        except Exception as ex:
            self.cbLog("warning", "Problem starting Bluetooth scan, type: " + str(type(ex)) + ", args: " + str(ex.args))
            return False

    def tryScan(self):
        d = threads.deferToThread(self.startScan)
        d.addCallback(self.checkStartScan)

    def checkStartScan(self, started):
        if started:
            self.cbLog("info", "Bluetooth scan started")
            self.scan()
        else:
            self.cbLog("warning", "Could not start BLE scan, retrying in " + str(TRY_START_INTERVAL) + " seconds")
            reactor.callLater(TRY_START_INTERVAL, self.tryScan)

    def scan(self):
        returnedList = blescan.parse_events(self.sock, 2)
        #self.cbLog("debug", "----------")
        for beacon in returnedList:
            #self.cbLog("debug", str(beacon))
            b = beacon.split(",")
            data = {"address": b[0],
                    "uuid": b[1].upper(),
                    "major": int(b[2]),
                    "minor": int(b[3]),
                    "reference_power": int(b[4]),
                    "rx_power": int(b[5])
                   }
            #self.cbLog("debug", "scan, sending: " + str(json.dumps(data, indent=4)))
            self.sendCharacteristic("ble_beacon", data, time.time())
        reactor.callLater(0.5, self.scan)

    def onAppInit(self, message):
        """
        Processes requests from apps.
        Called in a thread and so it is OK if it blocks.
        Called separately for every app that can make requests.
        """
        tagStatus = "ok"
        resp = {"name": self.name,
                "id": self.id,
                "status": tagStatus,
                "service": [{"characteristic": "ble_beacon",
                             "interval": 1.0}],
                "content": "service"}
        self.sendMessage(resp, message["id"])
        self.setState("running")
        
    def onAppRequest(self, message):
        self.cbLog("debug", "onAppRequest: " + str(json.dumps(message, indent=4)))
        # Switch off anything that already exists for this app
        for u in self.uuids:
            if message["id"] in u:
                self.uuids[u].remove(message["id"])
        # Now update details based on the message
        for f in message["service"]:
            if f["characteristic"] == "ble_beacon":
                for u in f["uuids"]:
                    if u not in self.uuids:
                        self.uuids[u] = [message["id"]]
                    else:
                        self.uuids[u].append(message["id"])
        self.cbLog("debug", "uuids: " + str(json.dumps(self.uuids, indent=4)))

    def onAppCommand(self, message):
        if "data" not in message:
            self.cbLog("warning", "app message without data: " + str(message))
        else:
            self.cbLog("warning", "This is a sensor. Message not understood: " +  str(message))

    def onConfigureMessage(self, config):
        """Config is based on what apps are to be connected.
            May be called again if there is a new configuration, which
            could be because a new app has been added.
        """
        self.tryScan()
        self.setState("starting")

if __name__ == '__main__':
    adaptor = Adaptor(sys.argv)
