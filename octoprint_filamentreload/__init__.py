# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.events import eventManager, Events
from flask import jsonify, make_response
import RPi.GPIO as GPIO

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

    def on_after_startup(self):
        self._logger.info("Filament Sensor Reloaded started")
        self.pin = int(self._settings.get(["pin"]))
        self.bounce = int(self._settings.get(["bounce"]))
        self.switch = int(self._settings.get(["switch"]))

        if self._settings.get(["pin"]) != -1:   # If a pin is defined
            self._logger.info("Filament Sensor active on GPIO Pin [%s]"%self.pin)
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)    # Initialize GPIO as INPUT

    def get_settings_defaults(self):
        return dict(
            pin     = -1,   # Default is no pin
            bounce  = 250,  # Debounce 250ms
            switch  = 0    # Normally Open
        )

    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=False)]

    def on_event(self, event, payload):
        if event == Events.PRINT_STARTED:  # If a new print is beginning
            self._logger.info("Printing started: Filament sensor enabled")
            if self.pin != -1:
                GPIO.add_event_detect(self.pin, GPIO.BOTH, callback=self.check_gpio, bouncetime=self.bounce)
        elif event in (Events.PRINT_DONE, Events.PRINT_FAILED, Events.PRINT_CANCELLED):
            self._logger.info("Printing stopped: Filament sensor disabled")
            try:
                GPIO.remove_event_detect(self.pin)
            except Exception:
                pass

    def check_gpio(self, channel):
        state = GPIO.input(self.pin)
        self._logger.debug("Detected sensor [%s] state [%s]"%(channel, state))
        if state != self.switch:    # If the sensor is tripped
            self._logger.debug("Sensor [%s]"%state)
            if self._printer.is_printing():
                self._printer.toggle_pause_print()

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
