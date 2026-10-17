package dev.fqih.hub

import org.junit.Assert.assertEquals
import org.junit.Test

class GridTest {
    @Test
    fun keepsNewestWeeksThatFit() {
        val weeks = (0 until 53).map { w -> List(7) { w } }
        val shown = Grid.visible(weeks, widthPx = 120, cellPx = 10, gapPx = 2)
        assertEquals(10, shown.size) // 10 * 10 + 9 * 2 = 118 <= 120
        assertEquals(52, shown.last()[0])
    }

    @Test
    fun fewerWeeksThanRoomShowsAll() {
        assertEquals(2, Grid.visible(listOf(List(7) { 0 }, List(7) { 1 }), 500, 10, 2).size)
    }

    @Test
    fun levelAlphaRisesWithActivity() {
        val alphas = (0..4).map { Grid.alpha(it) }
        assertEquals(alphas.sorted(), alphas)
        assertEquals(0, Grid.alpha(-1))
    }
}
