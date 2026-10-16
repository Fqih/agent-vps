package dev.fqih.hub

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import java.net.InetAddress
import java.net.ServerSocket
import kotlin.concurrent.thread

class StatusFetcherTest {
    // com.sun.net.httpserver is not on the Android unit-test classpath; a raw socket is enough here.
    private var server: ServerSocket? = null

    private fun serve(code: Int, body: String, extraHeader: String = ""): String {
        val s = ServerSocket(0, 1, InetAddress.getLoopbackAddress())
        thread(isDaemon = true) {
            runCatching {
                while (true) {
                    s.accept().use { c ->
                        val input = c.getInputStream().bufferedReader()
                        while (input.readLine()?.isNotEmpty() == true) Unit // skip request headers
                        val bytes = body.toByteArray()
                        c.getOutputStream().write(
                            ("HTTP/1.1 $code X\r\n$extraHeader" + "Content-Length: ${bytes.size}\r\nConnection: close\r\n\r\n").toByteArray() + bytes
                        )
                    }
                }
            }
        }
        server = s
        return "http://127.0.0.1:${s.localPort}/status?token=rahasia"
    }

    @After
    fun stop() {
        server?.close()
    }

    private fun message(r: Result<String>) = r.exceptionOrNull()?.message

    @Test
    fun okReturnsRawJson() {
        val r = StatusFetcher.fetch(serve(200, """{"level":"ok"}"""))
        assertEquals("""{"level":"ok"}""", r.getOrNull())
    }

    @Test
    fun redirectIsNotFollowed() {
        val target = serve(200, """{"level":"ok"}""")
        val first = server
        val redirect = serve(302, "", "Location: $target\r\n")
        try {
            assertEquals("HTTP 302", message(StatusFetcher.fetch(redirect)))
        } finally {
            first?.close()
        }
    }

    @Test
    fun forbiddenMeansBadToken() {
        assertEquals("token salah", message(StatusFetcher.fetch(serve(403, "forbidden"))))
    }

    @Test
    fun otherStatusShowsCode() {
        assertEquals("HTTP 500", message(StatusFetcher.fetch(serve(500, "boom"))))
    }

    @Test
    fun nonJsonIsBrokenData() {
        assertEquals("data rusak", message(StatusFetcher.fetch(serve(200, "<html>"))))
    }

    @Test
    fun unreachableIsOffline() {
        val url = serve(200, "{}")
        server!!.close()
        server = null
        assertEquals("offline", message(StatusFetcher.fetch(url, timeoutMs = 2_000)))
    }

    @Test
    fun errorHidesToken() {
        val url = serve(200, "{}")
        server!!.close()
        server = null
        assertFalse(message(StatusFetcher.fetch(url, timeoutMs = 2_000))!!.contains("rahasia"))
    }
}
