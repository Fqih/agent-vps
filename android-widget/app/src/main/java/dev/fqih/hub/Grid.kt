package dev.fqih.hub

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF

/** GitHub-style contribution squares in white at rising opacity, drawn into a bitmap. */
object Grid {
    /** The newest weeks that fit in [widthPx]. */
    fun visible(weeks: List<List<Int>>, widthPx: Int, cellPx: Int, gapPx: Int): List<List<Int>> =
        weeks.takeLast(((widthPx + gapPx) / (cellPx + gapPx)).coerceAtLeast(0))

    fun alpha(level: Int): Int = when (level) { 0 -> 0x1F; 1 -> 0x55; 2 -> 0x88; 3 -> 0xBB; 4 -> 0xF2; else -> 0 }

    fun bitmap(weeks: List<List<Int>>, widthPx: Int, cellPx: Int, gapPx: Int): Bitmap {
        val shown = visible(weeks, widthPx, cellPx, gapPx)
        val bmp = Bitmap.createBitmap(widthPx.coerceAtLeast(1), 7 * cellPx + 6 * gapPx, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        val radius = cellPx * 0.22f
        val left = widthPx - (shown.size * (cellPx + gapPx) - gapPx) // newest week on the right edge
        shown.forEachIndexed { w, days ->
            days.forEachIndexed { d, level ->
                if (level < 0) return@forEachIndexed
                paint.color = (alpha(level) shl 24) or 0xFFFFFF
                val x = (left + w * (cellPx + gapPx)).toFloat()
                val y = (d * (cellPx + gapPx)).toFloat()
                canvas.drawRoundRect(RectF(x, y, x + cellPx, y + cellPx), radius, radius, paint)
            }
        }
        return bmp
    }
}
