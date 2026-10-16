package dev.fqih.hub

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class UrlRulesTest {
    @Test
    fun acceptsTailnetStatusUrls() {
        assertNull(UrlRules.problem("http://100.64.0.1:8090/status?token=abc"))
        assertNull(UrlRules.problem("  http://box.example.ts.net:8090/status?token=abc  "))
        assertNull(UrlRules.problem("https://100.127.255.254/status?x=1&token=abc"))
    }

    @Test
    fun rejectsEverythingElse() {
        listOf(
            "http://192.168.1.2:8090/status?token=abc",
            "http://8.8.8.8/status?token=abc",
            "http://100.128.0.1/status?token=abc",
            "http://example.com/status?token=abc",
            "ftp://100.64.0.1/status?token=abc",
            "http://100.64.0.1:8090/?token=abc",
            "http://100.64.0.1:8090/status",
            "http://100.64.0.1:8090/status?token=",
            "not a url",
            "",
        ).forEach { assertNotNull(it, UrlRules.problem(it)) }
    }

    @Test
    fun dashboardKeepsToken() {
        assertEquals("http://100.64.0.1:8090/?token=abc", UrlRules.dashboard(" http://100.64.0.1:8090/status?token=abc"))
    }

    @Test
    fun botLinkOptionalButHttps() {
        assertNull(UrlRules.botProblem(""))
        assertNull(UrlRules.botProblem("https://t.me/some_bot"))
        assertNotNull(UrlRules.botProblem("http://t.me/some_bot"))
    }
}
