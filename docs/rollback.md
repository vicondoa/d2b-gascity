# Rollback contract

This contract covers the standalone host cutover. The repository acceptance
fixture is credential-free and hermetic. A deployed host still needs a
redacted operator receipt; the fixture is not evidence that a host was
switched.

## Separate roots

- `<prototype-root>` is the stopped, blocked prototype root. It remains
  untouched and read-only for the rollback window. Do not adopt, copy,
  convert, chown, or make it writable.
- `/var/lib/d2b-gascity` is the clean standalone root. Bootstrap it from
  portable source with no legacy state. Only this root is writable by the new
  Gas City service.
- The old generation may reference `<prototype-root>` for inspection, but
  every old Gas City service is disabled and stopped. Its root and any
  snapshot remain read-only.
- The new service environment and unit writable paths must contain no
  prototype root or legacy state path. No root may be shared as a writable
  path.

## Rehearsal

Before creating standalone work:

1. Build the candidate generation without switching the host and compare its
   rendered service identity, environment, writable paths, and root
   references.
2. Confirm the old generation sees only `<prototype-root>`, with the old
   service disabled, stopped, and read-only.
3. Confirm the new generation starts from an empty
   `/var/lib/d2b-gascity` root and writes only there.
4. Rehearse `old -> new -> old -> new`. The old leg must remain stopped and
   read-only. The new leg must not copy, convert, chown, or write the
   prototype.
5. Repeat the old leg from a retained closure with no network. A failed new
   start must leave the old generation, prototype root, and prior manifest
   usable.

The repository fixture checks hashes, ownership, and modes across the
transitions. The host receipt must record the corresponding redacted values.

## Retention and offline rollback

Retain the required old and new system generations and store closures without
garbage collection until the approved rollback expiry. The old generation
must boot from its retained closure without network access. Do not begin
standalone work or public d2b cleanup when root separation, integrity,
retention, or offline rollback is incomplete.

The prototype root and any filesystem snapshot are root-owned, restrictively
permissioned, encrypted at rest where supported, integrity-manifested, and
inaccessible to the standalone unit. The integrity manifest records each
protected path's hash, owner, and mode. After expiry, securely destroy the
prototype snapshot and root and retain only the destruction record.

## Host receipt and U12 eligibility

`tests/fixtures/rollback/rehearsal-receipt.example.json` is a generic schema
example. It is intentionally marked `host_generated: false` and
`eligible_for_u12: false`. A real receipt is host-generated and redacted and
contains these rows:

- `root_separation`
- `prototype_integrity`
- `old_service_state`
- `clean_standalone_root`
- `new_service_paths`
- `generation_rehearsal`
- `failed_new_start`
- `retained_closures`
- `offline_rollback`
- `expiry_and_destruction`

U12 remains ineligible until every row is present with a passing result, the
receipt is host-generated and redacted, and the offline rollback row records
no network use. Host-private paths, authorities, identifiers, credentials,
and service dumps stay as placeholders or out of the receipt.
