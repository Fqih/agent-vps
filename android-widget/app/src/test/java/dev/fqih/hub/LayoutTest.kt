package dev.fqih.hub

import org.junit.Assert.assertEquals
import org.junit.Test

class LayoutTest {
    @Test
    fun picksSizeFromActualHeight() {
        assertEquals(Layout(Size.SMALL, false, 0), Layout.of(180f))
        assertEquals(Layout(Size.MEDIUM, false, 0), Layout.of(400f))
        assertEquals(Layout(Size.LARGE, false, 40), Layout.of(560f))
    }

    @Test
    fun largeAddsGithubThenGrowsCharts() {
        assertEquals(Layout(Size.LARGE, false, 119), Layout.of(639f))
        assertEquals(Layout(Size.LARGE, true, 40), Layout.of(680f))
        assertEquals(Layout(Size.LARGE, true, 120), Layout.of(900f))
    }
}
