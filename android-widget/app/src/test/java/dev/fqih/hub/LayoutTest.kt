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
        assertEquals(Layout(Size.LARGE, false, 99), Layout.of(619f))
        assertEquals(Layout(Size.LARGE, true, 40), Layout.of(620f))
        // POCO X6 Pro 4x7 measured ~654 dp: GitHub fits and the charts keep ~74 dp.
        assertEquals(Layout(Size.LARGE, true, 74), Layout.of(654f))
        assertEquals(Layout(Size.LARGE, true, 120), Layout.of(900f))
    }
}
