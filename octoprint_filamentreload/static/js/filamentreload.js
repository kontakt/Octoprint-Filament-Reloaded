
$(function() {
    function FilamentReloadedViewModel(parameters) {
        var self = this;

        self.filamentIcon = $("#filament_indicator")


        self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "filamentreload") {
                window.alert("mauvais plugin: "+ plugin);
                return;
            }
            self.updateIcon(data.filamentStatus);
            window.alert("bon plugin: "+ data.filamentStatus);
            self.isConnected(data.isConnected);
        };


        self.updateIcon = function(data){
            self.filamentIcon.removeClass("present").removeClass("empty").removeClass("unknown");
            self.filamentIcon.addClass(data);
        }


    }
    OCTOPRINT_VIEWMODELS.push([
        FilamentReloadedViewModel,

        // e.g. loginStateViewModel, settingsViewModel, ...
        [ "settingsViewModel" ],

        // e.g. #settings_plugin_discordremote, #tab_plugin_octorant, ...
        [ "#navbar_plugin_filament_indicator" ]
    ]);

});
