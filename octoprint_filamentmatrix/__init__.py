# coding=utf-8
from __future__ import absolute_import
import octoprint.plugin
from octoprint.events import Events
import RPi.GPIO as GPIO
from time import sleep
from flask import jsonify


class FilamentReloadedPlugin(octoprint.plugin.StartupPlugin,
							 octoprint.plugin.EventHandlerPlugin,
							 octoprint.plugin.TemplatePlugin,
							 octoprint.plugin.SettingsPlugin,
							 octoprint.plugin.BlueprintPlugin):

	def initialize(self):

		self._logger.info("Running RPi.GPIO version '{0}'".format(GPIO.VERSION))
	if GPIO.VERSION < "0.6":  # Need at least 0.6 for edge detection
		raise Exception("RPi.GPIO must be greater than 0.6")
	GPIO.setwarnings(False)  # Disable GPIO warnings


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
		self._logger.info(
			"Filament Sensor active on GPIO Pin [%s]" % self.pin)
		GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
	else:
		self._logger.info(
			"Pin not configured, won't work unless configured!")


def on_after_startup(self):
	self._logger.info("Filament Sensor Reloaded started")
	self._setup_sensor()


def get_settings_defaults(self):
	return dict(
		pin=-1,  # Default is no pin
		bounce=250,  # Debounce 250ms
		switch=0,  # Normally Open
		mode=0,  # Board Mode
		no_filament_gcode='',
		pause_print=True,
		prevent_print=True,
		send_gcode_only_once=False,  # Default set to False for backward compatibility
	)


def on_settings_save(self, data):
	octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
	self._setup_sensor()


def sensor_triggered(self):
	return self.triggered


def sensor_enabled(self):
	return self.pin != -1


def sensor_active(self):
	return self.active


def no_filament(self):
	return GPIO.input(self.pin) != self.switch


def get_template_configs(self):
	return [dict(type="settings", custom_bindings=False)]


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
			self.triggered = 0  # reset triggered state
			GPIO.remove_event_detect(self.pin)
			if not hasattr(self, 'active'):  # no activation yet
				self.active = 1
				GPIO.add_event_detect(
					self.pin, GPIO.BOTH,
					callback=self.sensor_callback,
					bouncetime=self.bounce
				)
			self.active = 1
	# Disable sensor
	elif event in (
			Events.PRINT_DONE,
			Events.PRINT_FAILED,
			Events.PRINT_CANCELLED,
			Events.ERROR
	):
		self._logger.info("%s: Disabling filament sensor." % (event))
		self.active = 0


def sensor_callback(self, _):
	sleep(self.bounce / 1000)
	if not self.sensor_active():
		self._logger.debug("Sensor callback but no active sensor.")

	# If we have previously triggered a state change we are still out
	# of filament. Log it and wait on a print resume or a new print job.
	if self.sensor_triggered():
		self._logger.info("Sensor callback but no trigger state change.")
		return
	# If we have previously triggered a state change we are still out
	# of filament. Log it and wait on a print resume or a new print job.
	# if self.sensor_triggered():
	# Make sure that we still out of filament
	#    self.triggered = self.no_filament
	#    self._logger.info("Sensor callback but no trigger state change.")
	#    return

	if self.no_filament():
		if self.triggered == 1:
			self._logger.info("Waiting for filament...")
			return
		self._logger.info("Out of filament!")
		# Set the triggered flag to check next callback
		self.triggered = 1
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
		# Set the triggered flag to check next callback
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
		)
	)


__plugin_name__ = "Filament Sensor Reloaded"
__plugin_version__ = "1.1.1"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = FilamentReloadedPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}
