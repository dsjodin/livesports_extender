# Home Assistant

SHL Arena calls a Home Assistant webhook for each game event, at the moment the event
shows on TV (its `play_at`), never earlier. Home Assistant decides what happens: lights,
a goal horn, a spoken scorer. Payloads are in `docs/PROTOCOL.md` (Webhooks).

## 1. Set up

1. Pick a webhook id, for example `shl-arena`. The URL is
   `http://<home assistant>:8123/api/webhook/shl-arena`.
2. Add the automations below (Settings → Automations → ⋮ → Edit in YAML, or
   `automations.yaml`). Replace the entity ids (`light.vardagsrum`,
   `media_player.vardagsrum`, `tts.google_translate_sv_se`) with your own.
3. In the phone app: Inställningar → Home Assistant: paste the URL, tick "Skicka till Home
   Assistant", choose the events, "Spara".
4. Test: Live → "Testa mål". It sends a goal for my team at once (`test: true`,
   `is_my_team: true`, my team's colour, TTS "Mål för Örebro Hockey! Det här är ett
   test."). The call and its result show under Inställningar → Home Assistant and in
   `/sim` (Webhook log).

`local_only: true` keeps the webhook to your own network. SHL Arena runs in Docker on
the same LAN, so its calls count as local.

Every payload has `event`, `game_uuid`, `test` and `sent_ms`. Goals also carry `side`,
`is_my_team`, `team_name`, `team_color`, `team_rgb`, `scorer`, `scorer_number`,
`assists`, `strength`, `score_home`, `score_away`, `period`, `time`, `tts_sv` and
`source` (`feed`, or `manual` for the MÅL! button).

A MÅL! press sends `shl_goal` at once (team and score, no scorer). When SHL's goal for
it arrives, no second `shl_goal` is sent, so lights and horn go off once, but the
scorer is not read out (the press's `tts_sv` is only "Mål för <lag>! <ställning>.").
Without a press, the feed goal brings the scorer's name.

## 2. Goal for my team: lights in team colour, horn, scorer

The light flashes in the team's colour for 15 s and then returns to how it was
(`scene.create` takes a snapshot first). `mode: restart` lets a quick second goal start
over.

```yaml
- alias: "SHL: mål för mitt lag"
  id: shl_goal_mine
  mode: restart
  triggers:
    - trigger: webhook
      webhook_id: shl-arena
      allowed_methods: [POST]
      local_only: true
  conditions:
    - condition: template
      value_template: "{{ trigger.json.event == 'shl_goal' and trigger.json.is_my_team }}"
  actions:
    - action: scene.create
      data:
        scene_id: shl_before_goal
        snapshot_entities:
          - light.vardagsrum
    - action: light.turn_on
      target:
        entity_id: light.vardagsrum
      data:
        rgb_color: "{{ trigger.json.team_rgb or [245, 197, 66] }}"
        brightness_pct: 100
    - action: media_player.play_media
      target:
        entity_id: media_player.vardagsrum
      data:
        media_content_id: "media-source://media_source/local/malhorn.mp3"
        media_content_type: music
    - delay: "00:00:08"
    - if:
        - condition: template
          value_template: "{{ trigger.json.scorer != '' }}"
      then:
        - action: tts.speak
          target:
            entity_id: tts.google_translate_sv_se
          data:
            media_player_entity_id: media_player.vardagsrum
            message: "{{ trigger.json.tts_sv }}"
            language: sv
    - delay: "00:00:07"
    - action: scene.turn_on
      target:
        entity_id: scene.shl_before_goal
```

Put the horn file in `/media/malhorn.mp3` (Media → Local media). Bulbs that support it can
use `flash: long` on `light.turn_on` instead of the colour change.

## 3. Goal against: a short dim

```yaml
- alias: "SHL: mål mot mitt lag"
  id: shl_goal_against
  mode: restart
  triggers:
    - trigger: webhook
      webhook_id: shl-arena
      allowed_methods: [POST]
      local_only: true
  conditions:
    - condition: template
      value_template: >
        {{ trigger.json.event == 'shl_goal' and not trigger.json.is_my_team
           and not trigger.json.test }}
  actions:
    - action: scene.create
      data:
        scene_id: shl_before_against
        snapshot_entities:
          - light.vardagsrum
    - action: light.turn_on
      target:
        entity_id: light.vardagsrum
      data:
        brightness_pct: 20
    - delay: "00:00:05"
    - action: scene.turn_on
      target:
        entity_id: scene.shl_before_against
```

Every goal counts as "not my team" when no side is mine for the game (Matcher's "Inget",
or my team not playing); add `and trigger.json.side` checks if you only want real games.

## 4. Disallowed goal

```yaml
- alias: "SHL: mål underkänt"
  id: shl_goal_disallowed
  triggers:
    - trigger: webhook
      webhook_id: shl-arena
      allowed_methods: [POST]
      local_only: true
  conditions:
    - condition: template
      value_template: "{{ trigger.json.event == 'shl_goal_disallowed' and trigger.json.is_my_team }}"
  actions:
    - action: media_player.media_stop
      target:
        entity_id: media_player.vardagsrum
    - action: scene.turn_on
      target:
        entity_id: scene.shl_before_goal
```

## 5. Periods and the end of the game

```yaml
- alias: "SHL: period och matchslut"
  id: shl_periods
  mode: queued
  triggers:
    - trigger: webhook
      webhook_id: shl-arena
      allowed_methods: [POST]
      local_only: true
  actions:
    - choose:
        - conditions: "{{ trigger.json.event == 'shl_period_start' }}"
          sequence:
            - action: light.turn_on
              target:
                entity_id: light.vardagsrum
              data:
                brightness_pct: 60
        - conditions: "{{ trigger.json.event == 'shl_period_end' }}"
          sequence:
            - action: light.turn_on
              target:
                entity_id: light.vardagsrum
              data:
                brightness_pct: 100
        - conditions: "{{ trigger.json.event == 'shl_game_end' and trigger.json.my_team_won }}"
          sequence:
            - action: tts.speak
              target:
                entity_id: tts.google_translate_sv_se
              data:
                media_player_entity_id: media_player.vardagsrum
                message: "Seger! {{ trigger.json.score_home }}–{{ trigger.json.score_away }}."
                language: sv
```

`shl_period_start` and `shl_period_end` carry `period`; `shl_game_end` carries
`score_home`, `score_away`, `winner_side`, `my_team_won` (null when no side is mine),
`overtime` and `shootout`. `shl_penalty` carries `side`, `is_my_team`, `player`,
`number`, `offence_text` and `minutes`.

## Notes

- Older Home Assistant (before 2024.10) writes `trigger:` / `platform: webhook` and
  `action:` / `service:` instead of `triggers:` / `trigger:` and `actions:` / `action:`.
- Calls time out after 3 s and are retried once after 1 s. A replay seek or a new source
  cancels calls that have not been sent yet.
- Replays send webhooks too. Turn "Skicka till Home Assistant" off when testing replays
  late at night.
