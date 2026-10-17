package dev.fqih.hub

enum class Size { SMALL, MEDIUM, LARGE }

/** Which layout a widget of a given height gets; [chart] is the chart height in dp (0 = no charts). */
data class Layout(val size: Size, val github: Boolean, val chart: Int) {
    companion object {
        const val MEDIUM = 330f
        const val LARGE = 560f
        const val GITHUB = 680f

        fun of(heightDp: Float): Layout {
            val size = when {
                heightDp >= LARGE -> Size.LARGE
                heightDp >= MEDIUM -> Size.MEDIUM
                else -> Size.SMALL
            }
            if (size != Size.LARGE) return Layout(size, false, 0)
            // Large content fits LARGE; GitHub needs GITHUB; the charts take what a taller widget adds.
            val github = heightDp >= GITHUB
            val base = if (github) GITHUB else LARGE
            return Layout(size, github, (40 + (heightDp - base).toInt()).coerceIn(40, 120))
        }
    }
}
