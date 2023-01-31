# coding=utf-8
from __future__ import absolute_import
import octoprint.plugin
from octoprint.events import Events
import RPi.GPIO as GPIO
from time import sleep
from flask import jsonify
from threading import Thread


class FilamentReloadedPlugin(octoprint.plugin.StartupPlugin,
                             octoprint.plugin.EventHandlerPlugin,
                             octoprint.plugin.TemplatePlugin,
                             octoprint.plugin.SettingsPlugin,
                             octoprint.plugin.AssetPlugin,
                             octoprint.plugin.BlueprintPlugin
                             ):
    active = 0
    class filamentStatusWatcher(Thread):

        running = False

        def __init__(self):
            Thread.__init__(self)
            self.wCurrentState = -1

        def populate(self, wPluginManager, wIdentifier ,wCheckRate, wLogger):
            self._logger=wLogger
            self.wPluginManager = wPluginManager
            self.wIdentifier = wIdentifier
            self.wCheckRate = wCheckRate

        def run(self):
            self.running= True
            while self.running==True:
                self.updateIcon()
                sleep(self.wCheckRate/1000)

        def stopWatch(self):
            if self.running==True:
                self.running=False

        def updateIcon(self):
            if self.wCurrentState==0:
                self._logger.debug("Thread: Update icon 0")
                self.wPluginManager.send_plugin_message(self.wIdentifier, dict(filamentStatus="empty"))
            elif self.wCurrentState==1:
                self._logger.debug("Thread: Update icon 1")
                self.wPluginManager.send_plugin_message(self.wIdentifier, dict(filamentStatus="present"))
            elif self.wCurrentState==-1:
                self._logger.debug("Thread: Update icon 2")
                self.wPluginManager.send_plugin_message(self.wIdentifier, dict(filamentStatus="unknown"))

    filamentStatusWatcher = filamentStatusWatcher()

    def initialize(self):
        self._logger.info(
            "Running RPi.GPIO version '{0}'".format(GPIO.VERSION))
        if GPIO.VERSION < "0.6":       # Need at least 0.6 for edge detection
            raise Exception("RPi.GPIO must be greater than 0.6")
        GPIO.setwarnings(False)        # Disable GPIO warnings
        self.pin_value = -1			   # Cache the pin value when we detect out of filament

    @octoprint.plugin.BlueprintPlugin.route("/status", methods=["GET"])
    def check_status(self):
        status = "-1"
        if self.sensor_enabled():
            status = "0" if self.no_filament() else "1"
        return jsonify(status=status)

    @property
    def pin(self):
        return int(self._settings.get(["pin"]))

    @property
    def bounce(self):
        return int(self._settings.get(["bounce"]))

    @property
    def checkrate(self):
        return int(self._settings.get(["checkrate"]))

    @property
    def switch(self):
        return int(self._settings.get(["switch"]))

    @property
    def mode(self):
        return int(self._settings.get(["mode"]))

    @property
    def pullup(self):
        return int(self._settings.get(["pullup"]))

    @property
    def no_filament_gcode(self):
        return str(self._settings.get(["no_filament_gcode"])).splitlines()

    @property
    def pause_print(self):
        return self._settings.get_boolean(["pause_print"])

    @property
    def prevent_print(self):
        return self._settings.get_boolean(["prevent_print"])

    @property
    def send_gcode_only_once(self):
        return self._settings.get_boolean(["send_gcode_only_once"])

    def _setup_sensor(self):
        if self.sensor_enabled():
            self._logger.info("Setting up sensor.")
            if self.mode == 0:
                self._logger.info("Using Board Mode")
                GPIO.setmode(GPIO.BOARD)
            else:
                self._logger.info("Using BCM Mode")
                GPIO.setmode(GPIO.BCM)

            self._logger.info("Filament Sensor active on GPIO Pin [%s]"%self.pin)

            if self.pullup == 0:
                GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                self._logger.info("Filament Sensor Pin uses pullup")
            else:
                GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                self._logger.info("Filament Sensor Pin uses pulldown")

            if self.filamentStatusWatcher.running == False:
                self.filamentStatusWatcher.populate(self._plugin_manager, self._identifier, self.checkrate,self._logger)
                self.filamentStatusWatcher.daemon = True
                self.filamentStatusWatcher.start()
            else:
                self._logger.info("Setting new checkrate")
                self.filamentStatusWatcher.wCheckRate = self.checkrate
            self.no_filament()#to update the watcher's status

            GPIO.remove_event_detect(self.pin)
            GPIO.add_event_detect(
                self.pin, GPIO.BOTH,
                callback=self.sensor_callback,
                bouncetime=self.bounce
            )
        else:
            self._logger.info(
                "Pin not configured, won't work unless configured!")

    def on_after_startup(self):
        self._logger.info("Filament Sensor Reloaded started")
        self._setup_sensor()

    def get_settings_defaults(self):
        return dict(
            pin=-1,   # Default is no pin
            bounce=250,  # Debounce 250ms
            switch=0,    # Normally Open
            mode=0,    # Board Mode
	    pullup=0,  # Pullup or Pull Down - default is Pull up
            no_filament_gcode='',
            pause_print=True,
            prevent_print=True,
            send_gcode_only_once=False,  # Default set to False for backward compatibility
            checkrate = 1500, #navbar icon check frequency
        )

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._setup_sensor()

    def sensor_triggered(self):
        return self.triggered

    def sensor_enabled(self):
        return self.pin != -1

    def no_filament(self):
        nofilament = GPIO.input(self.pin) != self.switch
        self.filamentStatusWatcher.wCurrentState= int(not(nofilament))
        return nofilament

    ##~~ AssetPlugin mixin
    def get_assets(self):
        return {
            "js": ["js/filamentreload.js"],
            "less": ["less/filamentreload.less"],
            "css": ["css/filamentreload.css"]
            }
    # return dict(js=["js/filamentreload.js"],css=["css/filamentreload.css"],less=["less/psucontrol.less"],)


    def get_template_configs(self):
        return [
            dict(type="navbar", custom_bindings=False),
            dict(type="settings", custom_bindings=False)
        ]

    def on_event(self, event, payload):
        # Early abort in case of out ot filament when start printing, as we
        # can't change with a cold nozzle
        if event is Events.PRINT_STARTED and self.no_filament() and self.prevent_print:
            self._logger.info("Printing aborted: no filament detected!")
            self._printer.cancel_print()

        # Enable sensor
        if event in (
            Events.PRINT_STARTED,
            Events.PRINT_RESUMED
        ):
            if self.prevent_print and self.no_filament():
                self._logger.info(
                    "Printing paused: request to resume but no filament detected!")
                self._printer.pause_print()
            self._logger.info("%s: Enabling filament sensor." % (event))
            if self.sensor_enabled():
                self.triggered = 0 # reset triggered state
                self.active = 1
                GPIO.remove_event_detect(self.pin)
                self._logger.info("Filament present, print starting")
                GPIO.add_event_detect(
                        self.pin, GPIO.BOTH,
                        callback=self.sensor_callback,
                        bouncetime=self.bounce
                    )
        # Disable sensor
        elif event in (
            Events.PRINT_DONE,
            Events.PRINT_FAILED,
            Events.PRINT_CANCELLED,
            Events.PRINT_PAUSED,
            Events.ERROR
        ):
            self._logger.info("%s: Disabling filament sensor." % (event))
            self.active = 0

    def sensor_callback(self, _):
        sleep(self.bounce/1000)
        pin_triggered = GPIO.input(self.pin)

        self._logger.info("The value of the pin is {}. No filament = {} input = {}".format(pin_triggered, self.no_filament(), _))
        if not self.active:
            self._logger.debug("Sensor callback but no active sensor.")
            return
        # If we have previously triggered a state change we are still out
        # of filament. Log it and wait on a print resume or a new print job.
        if self.sensor_triggered():
            self._logger.info("Sensor callback with triggered set")
            #
            # Check to see if this is a spurious call back by the GPIO change system.  We have cached the
            # value of the sensor in self.pin_value.  If they are the same then we simply return
            if self.pin_value == pin_triggered:
                self._logger.info("Looks like we had one spurious callback , nothing to do, return")
                return
            else:
                self._logger.info("The pin is different lets process it.")

        self.pin_value = pin_triggered

        if self.no_filament():
            if self.triggered == 1:
                self._logger.info("Waiting for filament...")
                return
            # Set the triggered flag to check next callback
            self.triggered = 1
            self._logger.info("Out of filament!")
            if self.send_gcode_only_once:
                self._logger.info("Sending GCODE only once...")
            else:
                # Need to resend GCODE (old default) so reset trigger
                self.triggered = 0
            if self.pause_print:
                self._logger.info("Pausing print.")
                self._printer.pause_print()
            if self.no_filament_gcode:
                self._logger.info("Sending out of filament GCODE")
                self._printer.commands(self.no_filament_gcode)
        else:
            self._logger.debug("Filament detected!")
            # Set the triggered flag to check next callbacks
            self.triggered = 0

    def get_update_information(self):
        return dict(
            octoprint_filament=dict(
                displayName="Filament Sensor Reloaded",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="ssorgatem",
                repo="Octoprint-Filament-Reloaded",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/ssorgatem/Octoprint-Filament-Reloaded/archive/{target_version}.zip"
            ))


__plugin_name__ = "Filament Sensor Reloaded"
__plugin_version__ = "1.4.0"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamentReloadedPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
