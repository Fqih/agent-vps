package dev.fqih.hub

import org.junit.Assert.assertEquals
import org.junit.Test

class ChartTest {
    @Test
    fun mapsPercentToHeightOldestLeft() {
        assertEquals(listOf(0f to 100f, 50f to 50f, 100f to 0f), Chart.points(listOf(0, 50, 100), 100f, 100f))
    }

    @Test
    fun clampsOutOfRange() {
        assertEquals(listOf(0f to 100f, 10f to 0f), Chart.points(listOf(-5, 140), 10f, 100f))
    }

    @Test
    fun singleSampleDrawsFlatLine() {
        assertEquals(listOf(0f to 75f, 40f to 75f), Chart.points(listOf(25), 40f, 100f))
    }

    @Test
    fun noSamplesNoLine() {
        assertEquals(emptyList<Pair<Float, Float>>(), Chart.points(emptyList(), 40f, 100f))
    }
}
