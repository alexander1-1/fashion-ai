"""Тесты правил стадии/типа (кейсы из чеклиста п. 9 инструкции). Запуск: pytest tests/test_trends.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from trends import score_stage, classify_type


def _m(**kw):
    base = dict(p_share=0.0, p_growth=None, p_season="", m=0, f=0, i=0,
                s_growth=None, q_freq=0.0, q_growth=None, q_decline_months=0,
                c_cards=None, c_top_revenue=None)
    base.update(kw)
    return base


def _run(m):
    stage, _ = score_stage(m)
    ttype, _ = classify_type(m, stage)
    return stage, ttype


def test_lace_boudoir_early_majority():
    # кружево/будуар: массовый рост Q, ниша насыщается
    stage, ttype = _run(_m(p_share=.05, p_growth=1.5, m=5, f=8, i=20,
                           q_freq=45000, q_growth=.3, c_cards=400, c_top_revenue=5e6))
    assert stage == "РАННЕЕ БОЛЬШИНСТВО" and ttype == 2


def test_leopard_jeans_late_majority():
    # леопардовые джинсы: Q плато при высокой частотности
    stage, ttype = _run(_m(p_share=.02, p_growth=1.0, m=2, f=10, i=5,
                           q_freq=80000, q_growth=-.05, q_decline_months=1,
                           c_cards=900, c_top_revenue=8e6))
    assert stage == "ПОЗДНЕЕ БОЛЬШИНСТВО" and ttype == 2


def test_decline():
    stage, _ = _run(_m(q_freq=30000, q_growth=-.2, q_decline_months=3,
                       c_cards=700, f=3, i=1))
    assert stage == "СПАД"


def test_early_adopters_pilot_moment():
    # первые дропы middle + первый рост Q с низкой базы → пилотная партия
    stage, ttype = _run(_m(p_share=.036, p_growth=1.6, m=3, f=1, i=8,
                           q_freq=3000, q_growth=.6, c_cards=20))
    assert stage == "РАННИЕ ПОСЛЕДОВАТЕЛИ"
    assert ttype == 3  # Q уже есть (не ≈0) и растёт → подтверждённый, не тип 1


def test_type4_strong_analytics():
    stage, ttype = _run(_m(p_share=.03, p_growth=1.3, m=4, f=6, i=10,
                           q_freq=12000, q_growth=.2, c_cards=100, c_top_revenue=3e6))
    assert ttype == 4


def test_innovators_podium_only():
    # только подиум: P растёт, ниже сигналов нет — текущее состояние БД
    stage, ttype = _run(_m(p_share=.036, p_growth=1.8, i=1))
    assert stage == "ИННОВАТОРЫ" and ttype == 1
