# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.events import Events
import RPi.GPIO as GPIO
from time import sleep
from threading import Thread


class FilamentReloadedPlugin(octoprint.plugin.StartupPlugin,
                             octoprint.plugin.EventHandlerPlugin,
                             octoprint.plugin.TemplatePlugin,
                             octoprint.plugin.SettingsPlugin,
                             octoprint.plugin.AssetPlugin):

    class filamentStatusWatcher(Thread):

        running = False

        def __init__(self):
            Thread.__init__(self)

        def populate(self, wPluginManager, wIdentifier, wCurrentState,wCheckRate, wLogger):
            self._logger=wLogger
            self.wPluginManager = wPluginManager
            self.wIdentifier = wIdentifier
            self.wCurrentState = wCurrentState
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
            elif self.wCurrentState==2:
                self._logger.debug("Thread: Update icon 2")
                self.wPluginManager.send_plugin_message(self.wIdentifier, dict(filamentStatus="unknown"))

    state=2 #0 no filamenet , 1 filament present, 2 init
    last_state=2
    filamentStatusWatcher = filamentStatusWatcher()

    def initialize(self):
        self._logger.info("Running RPi.GPIO version '{0}'".format(GPIO.VERSION))
        if GPIO.VERSION < "0.6":       # Need at least 0.6 for edge detection
            raise Exception("RPi.GPIO must be greater than 0.6")
        GPIO.setwarnings(False)        # Disable GPIO warnings

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
    def no_filament_gcode(self):
        return str(self._settings.get(["no_filament_gcode"])).splitlines()

    @property
    def pause_print(self):
        return self._settings.get_boolean(["pause_print"])

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

            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            if self.filamentStatusWatcher.running == False:
                self.filamentStatusWatcher.populate(self._plugin_manager, self._identifier, self.state,self.checkrate,self._logger)
                self.filamentStatusWatcher.daemon = True
                self.filamentStatusWatcher.start()

                if self.no_filament():
                    pass
            else:
                self.filamentStatusWatcher.checkrate = self.checkrate()
                if self.no_filament():
                    pass

            GPIO.remove_event_detect(self.pin)
            GPIO.add_event_detect(
                self.pin, GPIO.BOTH,
                callback=self.sensor_callback,
                bouncetime=self.bounce
            )

        else:
            self._logger.info("Pin not configured, won't work unless configured!")

    def on_after_startup(self):
        self._logger.info("Filament Sensor Reloaded started")
        self._setup_sensor()

    def get_settings_defaults(self):
        return dict(
            pin     = -1,   # Default is no pin
            bounce  = 250,  # Debounce 250ms
            switch  = 0,    # Normally Open
            mode    = 0,    # Board Mode
            no_filament_gcode = '',
            pause_print = True,
            checkrate = 1500, #navbar icon check frequency
        )

    def on_settings_save(self, data):
        if(self.filamentStatusWatcher.running){
            self.filamentStatusWatcher.stopWatch()
        }
        sleep(0.2)
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        sleep(0.2)
        self._setup_sensor()

    def sensor_enabled(self):
        return self.pin != -1

    def no_filament(self):
        nofilament = GPIO.input(self.pin) != self.switch
        if nofilament:
            self.filamentStatusWatcher.wCurrentState=0
        else:
            self.filamentStatusWatcher.wCurrentState=1
        return nofilament

    ##~~ AssetPlugin mixin
    def get_assets(self):
        return dict(js=["js/filamentreload.js"],css=["css/filamentreload.css"])


    def get_template_configs(self):
        return [
            dict(type="navbar", custom_bindings=False),
            dict(type="settings", custom_bindings=False)
        ]

    def on_event(self, event, payload):
        # Early abort in case of out ot filament when start printing, as we
        # can't change with a cold nozzle
        if event is Events.PRINT_STARTED and self.no_filament():
            state=0
            self._logger.info("Printing aborted: no filament detected!")
            self._printer.cancel_print()

        # Enable sensor
        if event in (
            Events.PRINT_STARTED,
            Events.PRINT_RESUMED
        ):

            if self.no_filament():
                self.state=0
                pass
            else:
                self.state=1
                self._logger.info("%s: Enabling filament sensor." % (event))
                if self.sensor_enabled():
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
            #GPIO.remove_event_detect(self.pin)

    def sensor_callback(self, _):

        self._logger.debug("Last State Start Sensor: %d" %self.last_state)
        self._logger.debug("State Start Sensor: %d" %self.state)

        sleep(self.bounce/1000)
        if self.no_filament():
            self.state = 0
            if self.state != self.last_state:
                self._logger.info("Out of filament!")
                self.last_state = 0
                if self.pause_print:
                    self._logger.info("Pausing print.")
                    self._printer.pause_print()
                    #GPIO.remove_event_detect(self.pin)
                if self.no_filament_gcode:
                    self._logger.info("Sending out of filament GCODE")
                    self._printer.commands(self.no_filament_gcode)
                    #GPIO.remove_event_detect(self.pin)
        else:

            self.state = 1

            self._logger.debug("Last State Before if: %d" %self.last_state)
            self._logger.debug("State Before if: %d" %self.state)

            if self.state != self.last_state:
                self._logger.info("Filament present")
                self.last_state = 1

        self._logger.debug("Last State EndCB: %d" %self.last_state)
        self._logger.debug("State EndCB: %d" %self.state)

    def get_update_information(self):
        return dict(
            octoprint_filament=dict(
                displayName="Filament Sensor Reloaded",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="Floyz",
                repo="Octoprint-Filament-Reloaded",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/Floyz/Octoprint-Filament-Reloaded/archive/{target_version}.zip"
            )
        )

__plugin_name__ = "Filament Sensor Reloaded"
__plugin_version__ = "1.0.6"

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamentReloadedPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
}
