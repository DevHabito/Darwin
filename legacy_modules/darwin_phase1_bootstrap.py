
from __future__ import annotations

from dataclasses import asdict
from darwin_home import DarwinHome, compute_valence


def main() -> None:
    home = DarwinHome("darwin_home")
    home.bootstrap()

    self_model = home.load_self_model()
    state = home.load_current_state()
    policy = home.load_policy()

    print("Darwin Home inicializado com sucesso.")
    print(f"Nome    : {self_model['name']}")
    print(f"Versão  : {self_model['version']}")
    print(f"Missão  : {self_model['mission']}")
    print(f"Banco   : {home.db_path}")

    print("\nEstado atual:")
    print(asdict(state))

    print("\nPolicy atual:")
    print(asdict(policy))

    prev_sigma = state.sigma
    new_sigma = 1.32
    repeated_error = False

    pain, wellbeing = compute_valence(
        prev_sigma=prev_sigma,
        new_sigma=new_sigma,
        energy=state.energy,
        repeated_error=repeated_error,
    )

    state.sigma = new_sigma
    state.pain_signal = pain
    state.wellbeing_signal = wellbeing

    home.save_current_state(state)

    home.add_episode(
        module="bootstrap",
        context="criação inicial do Darwin Home",
        action_taken="bootstrap do espaço persistente local",
        outcome="success",
        lesson="Darwin agora possui uma casa persistente e não precisa reiniciar do zero.",
        sigma_before=prev_sigma,
        sigma_after=new_sigma,
    )

    home.upsert_semantic_memory(
        key="tic_tac_toe_core_rule",
        content="Bloquear ameaça imediata vem antes de construir vantagem futura.",
        confidence=0.95,
        source="manual_bootstrap",
    )

    snapshot = home.export_snapshot()
    print(f"\nSnapshot exportado em: {snapshot}")

    print("\nÚltimos episódios:")
    for ep in home.recent_episodes(limit=5):
        print(f"- [{ep['module']}] {ep['outcome']} | {ep['lesson']}")

    home.close()


if __name__ == "__main__":
    main()
