# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.events import eventManager, Events
from flask import jsonify, make_response
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
        GPIO.setmode(GPIO.BOARD)       # Use the board numbering scheme
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
    def after_pause_gcode(self):
        return str(self._settings.get(["after_pause_gcode"])).splitlines()

    @property
    def after_resume_gcode(self):
        return str(self._settings.get(["after_resume_gcode"])).splitlines()

    def on_after_startup(self):
        self._logger.info("Filament Sensor Reloaded started")
        if self.sensor_enabled():
            self._logger.info("Filament Sensor active on GPIO Pin [%s]"%self.pin)
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)    # Initialize GPIO as INPUT
        else:
            self._logger.info("Pin not configured, won't work unless configured!")

    def get_settings_defaults(self):
        return dict(
            pin     = -1,   # Default is no pin
            bounce  = 250,  # Debounce 250ms
            switch  = 0,    # Normally Open
            after_pause_gcode = '',
            after_resume_gcode = '',
        )

    def sensor_enabled(self):
        return self.pin != -1

    def no_filament(self):
        return GPIO.input(self.pin) != self.switch

    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=False)]

    @property
    def _filament_change(self):
        return self.__dict__.get('_filament_change', False)

    def on_event(self, event, payload):
        # Early abort in case of out ot filament when start printing, as we
        # can't change with a cold nozzle
        if event is Events.PRINT_STARTED and self.no_filament():
            self._logger.info("Printing aborted: no filament detected!")
            self._printer.cancel_print()
        # Run after resume gcode
        if event is Events.PRINT_RESUMED:
            if self._filament_change:
                self._logger.info("Sending after resume GCODE!")
                self._printer.commands(self.after_resume_gcode)
                self._filament_change = False
        # Enable sensor
        if event in (
            Events.PRINT_STARTED,
            Events.PRINT_RESUMED
        ):
            self._logger.info("%s: Enabling filament sensor." % (event))
            if self.sensor_enabled():
                GPIO.remove_event_detect(self.pin)
                GPIO.add_event_detect(self.pin, GPIO.BOTH, callback=self.sensor_callback, bouncetime=self.bounce)
        # Disable sensor
        elif event in (
            Events.PRINT_DONE,
            Events.PRINT_FAILED,
            Events.PRINT_CANCELLED,
            Events.ERROR
        ):
            self._logger.info("%s: Disabling filament sensor." % (event))
            GPIO.remove_event_detect(self.pin)

    def sensor_callback(self, _):
        sleep(self.bounce/1000)
        if self.no_filament():
            if self._filament_change:
                self._logger.info("Out of filament, waiting for replacement!")
            else:
                self._logger.info("Out of filament, pausing!")
                self._printer.pause_print()
                if self.after_pause_gcode:
                    self._logger.info("Sending after pause GCODE")
                    self._printer.commands(self.after_pause_gcode)
                self._filament_change = True
        else:
            self._logger.info("Filament detected, resume to continue!")

    def get_update_information(self):
        return dict(
            octoprint_filament=dict(
                displayName="Filament Sensor Reloaded",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="kontakt",
                repo="Octoprint-Filament-Reloaded",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/kontakt/Octoprint-Filament-Reloaded/archive/{target_version}.zip"
            )
        )

__plugin_name__ = "Filament Sensor Reloaded"
__plugin_version__ = "1.0.1"

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamentReloadedPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
}
