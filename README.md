# Ticklist

Offline-first phone ticklists for many-routes-in-a-day climbing challenges.
Each challenge is a YAML file baked into a static PWA page: routes in circuit
order with UKC links, guidebook topo photos, descent and changeover info
rendered between routes, timestamped ticks with pacing, all stored on-device.

Site: https://elcarl.github.io/climbing-ticklist-tracker/

## Use

```
make venv     # once
make test
make build    # bake challenges/ into docs/
make serve    # local preview on :8642
make deploy   # test + build + commit + push (GitHub Pages serves docs/)
```

## Adding a challenge

Copy `challenges/stanage-vs/` as a template. One `challenge.yaml` per
challenge plus a `topos/` directory of guidebook photos (JPEG-compressed at
build time; one photo can be shared by several routes via the `topo:` field).
Descent text renders in the transition row after the route; leader `blocks`
render changeover markers.

Tick data lives in localStorage on the phone under `ticklist:<slug>:v1`.
