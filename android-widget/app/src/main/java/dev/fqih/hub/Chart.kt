package dev.fqih.hub

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path

/** Sparkline for 0-100 percent samples, drawn into a bitmap because Glance has no canvas. */
object Chart {
    /** Oldest sample at x=0, newest at x=[width]; 100% at the top (y=0). */
    fun points(values: List<Int>, width: Float, height: Float): List<Pair<Float, Float>> {
        if (values.isEmpty()) return emptyList()
        val ys = values.map { height * (1 - it.coerceIn(0, 100) / 100f) }
        if (ys.size == 1) return listOf(0f to ys[0], width to ys[0])
        return ys.mapIndexed { i, y -> width * i / (ys.size - 1) to y }
    }

    fun bitmap(values: List<Int>, widthPx: Int, heightPx: Int, color: Int): Bitmap {
        val bmp = Bitmap.createBitmap(widthPx.coerceAtLeast(1), heightPx.coerceAtLeast(1), Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        val stroke = heightPx / 24f + 2f
        val pts = points(values, widthPx.toFloat(), heightPx - stroke).map { (x, y) -> x to y + stroke / 2 }
        val grid = Paint().apply { this.color = 0x1AFFFFFF; strokeWidth = 1f }
        listOf(0.5f).forEach { canvas.drawLine(0f, heightPx * it, widthPx.toFloat(), heightPx * it, grid) }
        if (pts.isEmpty()) return bmp
        val line = Path().apply { pts.forEachIndexed { i, (x, y) -> if (i == 0) moveTo(x, y) else lineTo(x, y) } }
        val area = Path(line).apply { lineTo(pts.last().first, heightPx.toFloat()); lineTo(0f, heightPx.toFloat()); close() }
        canvas.drawPath(area, Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = color and 0x00FFFFFF or 0x33000000 })
        canvas.drawPath(line, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            this.color = color; style = Paint.Style.STROKE; strokeWidth = stroke
            strokeJoin = Paint.Join.ROUND; strokeCap = Paint.Cap.ROUND
        })
        return bmp
    }
}
