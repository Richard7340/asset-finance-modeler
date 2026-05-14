from asset_finance_modeler.assets.saas.schema import (
    COGSConfig,
    LLMTier,
    PerActiveCustomerCosts,
    PerActiveUnitCosts,
    TwilioCost,
    VoiceProviderCost,
)


def test_llm_tier():
    t = LLMTier(
        model="sonnet-4-7",
        eur_per_million_input=3.0,
        eur_per_million_output=15.0,
        avg_tokens_in_per_month=800_000,
        avg_tokens_out_per_month=200_000,
    )
    assert t.monthly_cost_eur() == 5.4


def test_voice_provider_stt():
    v = VoiceProviderCost(provider="deepgram", eur_per_minute=0.0043, monthly_usage=200)
    assert v.monthly_cost_eur() == 0.0043 * 200


def test_voice_provider_tts():
    v = VoiceProviderCost(provider="cartesia", eur_per_million_chars=25, monthly_usage=50_000)
    assert v.monthly_cost_eur() == 1.25


def test_twilio_cost():
    t = TwilioCost(
        whatsapp_eur_per_msg=0.005,
        voice_eur_per_min=0.012,
        msgs_per_month=600,
        min_per_month=80,
    )
    assert t.monthly_cost_eur() == 3.96


def test_cogs_minimal():
    c = COGSConfig(
        per_active_unit=PerActiveUnitCosts(llm_tokens=[], infra_eur=2.0),
        per_active_customer=PerActiveCustomerCosts(),
    )
    assert c.per_active_customer.support_eur == 0
