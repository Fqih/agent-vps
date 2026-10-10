import unittest
from datetime import datetime, timedelta, timezone

import filters

NOW = datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc)


def job(**kw):
    base = {"title": "AI Engineer", "company": "Acme", "location": "Jakarta Selatan",
            "url": "https://www.example.com/jobs/1/", "posted": NOW - timedelta(days=1),
            "deadline": None, "snippet": ""}
    return {**base, **kw}


class CandidateJob(unittest.TestCase):
    def test_fresh_entry_jakarta_passes(self):
        self.assertTrue(filters.is_candidate_job(job(), NOW))

    def test_old_or_undated_dropped(self):
        self.assertFalse(filters.is_candidate_job(job(posted=NOW - timedelta(days=4)), NOW))
        self.assertFalse(filters.is_candidate_job(job(posted=None), NOW))

    def test_closed_deadline_dropped(self):
        self.assertFalse(filters.is_candidate_job(job(deadline=NOW - timedelta(hours=1)), NOW))

    def test_senior_titles_dropped(self):
        for t in ["Senior Data Scientist", "Sr. ML Engineer", "AI Lead", "Data Science Manager",
                  "AI Architect", "Machine Learning Intern"]:
            self.assertFalse(filters.is_candidate_job(job(title=t), NOW), t)

    def test_unrelated_role_dropped(self):
        self.assertFalse(filters.is_candidate_job(job(title="Frontend Developer"), NOW))
        self.assertFalse(filters.is_candidate_job(job(title="Email Marketing Specialist"), NOW))

    def test_many_years_dropped(self):
        self.assertFalse(filters.is_candidate_job(job(snippet="Minimal 5 tahun pengalaman"), NOW))
        self.assertFalse(filters.is_candidate_job(job(snippet="4+ years of experience"), NOW))
        self.assertTrue(filters.is_candidate_job(job(snippet="1-2 years experience"), NOW))

    def test_location(self):
        self.assertTrue(filters.is_candidate_job(job(location="Worldwide"), NOW))
        self.assertFalse(filters.is_candidate_job(job(location="Surabaya"), NOW))


class Dedupe(unittest.TestCase):
    def test_url_key_normalizes(self):
        self.assertEqual(filters.url_key("https://www.a.com/x/?utm=1"), filters.url_key("http://a.com/x"))

    def test_same_title_company_other_url_is_duplicate(self):
        a = job(url="https://a.com/1")
        b = job(url="https://b.com/2", title="AI  engineer", company="ACME")
        self.assertEqual(filters.dedupe([a, b], filters.job_keys), [a])


class Format(unittest.TestCase):
    def test_escapes_and_labels(self):
        text = filters.format_jobs("Rab 07 Okt 2026", [job(title="AI <Eng> & ML", why="cocok")], NOW, "footer")
        self.assertIn("1. <a", text)
        self.assertIn("AI &lt;Eng&gt; &amp; ML", text)
        self.assertIn("1 hari lalu", text)
        self.assertIn("tidak ada lowongan", filters.format_jobs("x", [], NOW, "f"))

    def test_news_has_no_jobs(self):
        text = filters.format_news("Rab", [], [], NOW)
        self.assertIn("tidak ada berita baru", text)
        self.assertNotIn("Lowongan", text)

    def test_age_label(self):
        self.assertEqual(filters.age_label(NOW - timedelta(minutes=10), NOW), "1 jam lalu")
        self.assertEqual(filters.age_label(None, NOW), "tanggal ?")


class HermesTranscript(unittest.TestCase):
    def test_ignores_prompt_echo_and_reads_final_box(self):
        raw = ('Jawaban akhir HANYA JSON array (boleh kosong []):\n'
               '╭─ ☤ Hermes ─────╮\n[\n  {"title": "DS", "url": "https://x"}\n]\n╰──────╯\nSession: 1')
        self.assertEqual(filters.final_json_array(raw), [{"title": "DS", "url": "https://x"}])

    def test_missing_box_or_bad_json(self):
        self.assertIsNone(filters.final_json_array("no box []"))
        self.assertIsNone(filters.final_json_array("╭─ ☤ Hermes ─╮\nsorry\n╰─╯"))


if __name__ == "__main__":
    unittest.main()
