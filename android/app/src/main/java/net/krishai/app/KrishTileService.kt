package net.krishai.app

import android.annotation.SuppressLint
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService

/** Quick-settings tile: swipe down from the top of the screen and tap Krish to start a new chat. */
class KrishTileService : TileService() {
    override fun onStartListening() {
        qsTile?.apply {
            state = Tile.STATE_INACTIVE
            updateTile()
        }
    }

    @SuppressLint("StartActivityAndCollapseDeprecated")
    override fun onClick() {
        if (Build.VERSION.SDK_INT >= 34) {
            startActivityAndCollapse(Krish.pendingIntent(this, "/?new=1", 3))
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(Krish.intent(this, "/?new=1"))
        }
    }
}
