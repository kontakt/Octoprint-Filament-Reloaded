# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.events import Events
import RPi.GPIO as GPIO
from time import sleep


class FilamentReloadedPlugin(octoprint.plugin.StartupPlugin,
                             octoprint.plugin.EventHandlerPlugin,
                             octoprint.plugin.TemplatePlugin,
                             octoprint.plugin.SettingsPlugin):

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
        )

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._setup_sensor()

    def sensor_enabled(self):
        return self.pin != -1

    def no_filament(self):
        return GPIO.input(self.pin) != self.switch

    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=False)]

    def on_event(self, event, payload):
        # Early abort in case of out ot filament when start printing, as we
        # can't change with a cold nozzle
        if event is Events.PRINT_STARTED and self.no_filament():
            self._logger.info("Printing aborted: no filament detected!")
            self._printer.cancel_print()

        # Enable sensor
        if event in (
            Events.PRINT_STARTED,
            Events.PRINT_RESUMED
        ):
            self._logger.info("%s: Enabling filament sensor." % (event))
            if self.sensor_enabled():
                GPIO.remove_event_detect(self.pin)
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
            GPIO.remove_event_detect(self.pin)

    def sensor_callback(self, _):

        #init last_state
        if 'last_state' in locals():
            pass
        else:
            last_state=2 #0 no filamenet , 1 filament present, 2 init

        sleep(self.bounce/1000)
        if self.no_filament():
            state = 0
            if state != last_state:
                self._logger.info("Out of filament!")
                last_state = 0
            if self.pause_print:
                self._logger.info("Pausing print.")
                self._printer.pause_print()
                GPIO.remove_event_detect(self.pin)
            if self.no_filament_gcode:
                self._logger.info("Sending out of filament GCODE")
                self._printer.commands(self.no_filament_gcode)
                GPIO.remove_event_detect(self.pin)
        else:
            state = 1
            if state != last_state:
                self._logger.info("Filament present")
                last_state = 1

        self._logger.debug("Last State: %d" %last_state)
        self._logger.debug("State: %d" %state)

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
__plugin_version__ = "1.0.3"

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamentReloadedPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
}
