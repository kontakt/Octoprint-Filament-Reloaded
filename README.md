# OctoPrint-FilamentReloaded

Based on the Octoprint-Filament plugin by MoonshineSG (https://github.com/MoonshineSG/Octoprint-Filament), this modification adds the ability to modify your configuration through OctoPrint settings, as well as adding configurations for both NO and NC switches.

Future developments are planned to include multiple filament sensors, pop-ups, pre-print validation and custom filament run-out scripting.

## Setup

Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager)
or manually using this URL:

    https://github.com/kontakt/Octoprint-Filament-Reloaded/archive/master.zip

Using this plugin requires a filament sensor. The code is set to use the Raspberry Pi's internal Pull-Up resistors, so the switch should be between your detection pin and a ground pin.
