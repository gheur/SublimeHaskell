
import os

import SublimeHaskell.sublime_haskell_common as Common
import SublimeHaskell.internals.settings as Settings
import SublimeHaskell.internals.proc_helper as ProcHelper


def plugin_loaded():
    cache_path = Common.sublime_haskell_cache_path()

    if not os.path.exists(cache_path):
        os.makedirs(cache_path)

    Settings.PLUGIN_SETTINGS.load()

    # Register change detection:
    Settings.PLUGIN_SETTINGS.add_change_callback('add_to_PATH', ProcHelper.ProcHelper.update_environment)
    Settings.PLUGIN_SETTINGS.add_change_callback('add_standard_dirs', ProcHelper.ProcHelper.update_environment)
