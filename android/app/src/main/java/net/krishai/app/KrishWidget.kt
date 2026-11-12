package net.krishai.app

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.widget.RemoteViews

/** Home-screen widget: a search bar that opens a new chat, and a mic that starts talking to Krish. */
class KrishWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val views = RemoteViews(context.packageName, R.layout.widget_krish).apply {
            val ask = Krish.pendingIntent(context, "/?new=1", 1)
            setOnClickPendingIntent(R.id.widget_root, ask)
            setOnClickPendingIntent(R.id.widget_ask, ask)
            setOnClickPendingIntent(R.id.widget_logo, ask)
            setOnClickPendingIntent(R.id.widget_mic, Krish.pendingIntent(context, "/?voice=1", 2))
        }
        manager.updateAppWidget(ids, views)
    }
}
