from urbanagent.verify import verify_answer


def test_percentage_from_fraction_is_traceable():
    r = verify_answer("La cuota de infraestructura es 12,5 %.", [0.125])
    assert r["ok"] and r["checked"] == 1


def test_thousands_separator_and_rounding():
    assert verify_answer("Hay 1.500 m de radio.", [1500])["ok"]
    assert verify_answer("Pendiente de 4,2 %.", [4.2371])["ok"]


def test_invented_number_is_flagged():
    r = verify_answer("Hay 4.321 edificios.", [1200, 3000])
    assert not r["ok"] and r["unverified"] == ["4.321"]


def test_small_integers_and_years_are_ignored():
    r = verify_answer("En 2026 se analizaron 3 zonas.", [])
    assert r["ok"] and r["checked"] == 0


def test_numbers_from_question_are_not_checked():
    r = verify_answer("Con radio de 2500 m.", [], question="Usa un radio de 2500 m")
    assert r["ok"]


def test_source_ids_are_not_treated_as_numbers():
    r = verify_answer("Fuente [S12] y S3.", [])
    assert r["ok"] and r["checked"] == 0
