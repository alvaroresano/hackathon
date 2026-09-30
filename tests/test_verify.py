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


def test_number_from_another_zone_is_flagged():
    # caso real (30-sep-2026): el modelo atribuyó a Tolosa la densidad de Eibar
    zones = {"Eibar": [3392.6, 7.25], "Tolosa": [2554.2, 3.49], "Zarautz": [3735.2, 0.93]}
    tool = [v for vs in zones.values() for v in vs]
    r = verify_answer("- En Tolosa, confirmar si la bici es viable con alta densidad (3393 hab/km²).", tool, zone_numbers=zones)
    assert not r["ok"]
    assert r["misattributed"] == [{"value": "3393", "line_zone": "Tolosa", "belongs_to": ["Eibar"]}]


def test_correct_zone_rows_pass_and_ambiguous_lines_are_skipped():
    zones = {"Eibar": [3392.6], "Tolosa": [2554.2], "Gros, Donostia": [10968.7], "Donostia": [14469.9]}
    tool = [v for vs in zones.values() for v in vs]
    ok = "| Eibar | 3393 |\n| Tolosa | 2554 |\nGros, Donostia: 10969 hab/km²\nEibar y Tolosa: 2554 y 3393."
    r = verify_answer(ok, tool, zone_numbers=zones)
    assert r["ok"], r


def test_english_thousands_separator():
    r = verify_answer("Población en el círculo: 56,164 y 45.784.", [56164, 45784])
    assert r["ok"], r


def test_comparison_lines_are_not_flagged_as_misattributed():
    # falso positivo real: "Gros obtiene 84.3 vs. 78.6" (78.6 es de Amara, pero la frase compara)
    zones = {"Gros, Donostia": [84.3], "Amara, Donostia": [78.6]}
    r = verify_answer("Gros obtiene una puntuación más alta (84.3 vs. 78.6).", [84.3, 78.6], zone_numbers=zones)
    assert r["ok"], r


def test_numbers_inside_tool_text_count_as_backed():
    from urbanagent.session import Session

    s = Session()
    s.record_tool_output({"note": "No es la población del círculo de 1.500 m que usan las zonas."})
    assert verify_answer("Radio de 1.500 m.", s.tool_numbers)["ok"]
