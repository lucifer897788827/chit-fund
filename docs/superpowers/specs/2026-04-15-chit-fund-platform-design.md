# Chit Fund Platform Design

**Date:** 2026-04-15

**Goal**

Design a fast, owner-scoped chit-fund platform for small chit operators, with realtime online auctions, subscriber participation, and private external chit tracking for both subscribers and participating chit owners.

**Product Shape**

The platform supports two parallel use cases:

1. `managed chits`
   Live multi-user chit groups operated inside the platform by a `chit_owner`. These support member enrollment, installment tracking, online bidding, auction results, and payout records.
2. `external chit records`
   Private personal tracking records maintained by any user who has a subscriber profile. These are simple logs for outside chits and do not participate in live bidding or shared system workflows.

## Roles

### `super_admin`

Platform-wide operator with access to all owners, subscribers, groups, payments, auctions, and audit records.

### `chit_owner`

Runs one owner workspace, creates and manages multiple chit groups, records payments, opens and closes auctions, finalizes results, and views reports.

### `subscriber`

Participates in managed chit groups, pays dues, bids online, views outcomes, and tracks private external chits.

## Identity Model

The system uses a single `users` table for authentication. A user's primary system role lives on the user record.

A separate `subscribers` profile table controls participant capabilities. This allows:

1. standard subscriber accounts
2. chit owners who also act as participants
3. private external chit tracking for any user with a subscriber profile

This means a chit owner may have:

1. an `owners` record for operator capabilities
2. a `subscribers` record for participant capabilities

Role-based permissions and subscriber capabilities are intentionally separate.

## Architecture

The system should be built as a modular monolith with a performance-sensitive auction path.

### Runtime Components

1. `frontend`
   React web application with separate operator and participant experiences.
2. `backend API`
   FastAPI service handling authentication, CRUD workflows, payments, and auction commands.
3. `PostgreSQL`
   Source of truth for all transactional data.
4. `Redis`
   Auction room state, websocket fanout, rate limiting, and short-lived finalization locks.
5. `background worker`
   Notifications, receipt generation, summaries, and non-critical post-auction work.
6. `object storage`
   Optional receipts, exported statements, and generated documents.

### Performance Model

The application must optimize around two modes:

1. `auction mode`
   Low-latency bid submission, minimal payloads, realtime updates, deterministic close/finalize behavior.
2. `management mode`
   Normal CRUD for group setup, payments, reports, subscriber management, and private external records.

Heavy work must never block auction operations.

## Domain Model

### Core Identity and Ownership

#### `users`

- `id`
- `email`
- `phone`
- `password_hash`
- `role` (`super_admin`, `chit_owner`, `subscriber`)
- `is_active`
- `last_login_at`
- `created_at`
- `updated_at`

#### `owners`

- `id`
- `user_id`
- `display_name`
- `business_name`
- `city`
- `state`
- `status`
- `created_at`
- `updated_at`

#### `subscribers`

- `id`
- `user_id`
- `owner_id` (nullable)
- `full_name`
- `phone`
- `email` (nullable)
- `address_text` (nullable)
- `status`
- `created_at`
- `updated_at`

### Managed Chit Domain

#### `chit_groups`

- `id`
- `owner_id`
- `group_code`
- `title`
- `chit_value`
- `installment_amount`
- `member_count`
- `cycle_count`
- `cycle_frequency`
- `start_date`
- `first_auction_date`
- `current_cycle_no`
- `bidding_enabled`
- `status` (`draft`, `open`, `active`, `completed`, `cancelled`)
- `created_at`
- `updated_at`

#### `group_memberships`

- `id`
- `group_id`
- `subscriber_id`
- `member_no`
- `joined_at`
- `membership_status` (`invited`, `active`, `exited`, `defaulted`)
- `prized_status` (`unprized`, `prized`)
- `prized_cycle_no` (nullable)
- `can_bid`
- `created_at`
- `updated_at`

#### `installments`

- `id`
- `group_id`
- `membership_id`
- `cycle_no`
- `due_date`
- `due_amount`
- `penalty_amount`
- `paid_amount`
- `balance_amount`
- `status` (`pending`, `partial`, `paid`, `overdue`, `waived`)
- `last_paid_at` (nullable)
- `created_at`
- `updated_at`

### Auction Domain

#### `auction_sessions`

- `id`
- `group_id`
- `cycle_no`
- `scheduled_start_at`
- `actual_start_at` (nullable)
- `actual_end_at` (nullable)
- `bidding_window_seconds`
- `status` (`scheduled`, `open`, `closed`, `finalized`, `cancelled`)
- `opened_by_user_id` (nullable)
- `closed_by_user_id` (nullable)
- `winning_bid_id` (nullable)
- `created_at`
- `updated_at`

#### `auction_bids`

- `id`
- `auction_session_id`
- `membership_id`
- `bidder_user_id`
- `bid_amount`
- `bid_discount_amount`
- `placed_at`
- `is_valid`
- `invalid_reason` (nullable)
- `supersedes_bid_id` (nullable)

#### `auction_results`

- `id`
- `auction_session_id`
- `group_id`
- `cycle_no`
- `winner_membership_id`
- `winning_bid_id`
- `winning_bid_amount`
- `dividend_pool_amount`
- `dividend_per_member_amount`
- `owner_commission_amount`
- `winner_payout_amount`
- `finalized_by_user_id`
- `finalized_at`
- `created_at`

### Money Domain

#### `payments`

- `id`
- `owner_id`
- `subscriber_id`
- `membership_id` (nullable)
- `installment_id` (nullable)
- `payment_type` (`installment`, `advance`, `penalty`, `adjustment`)
- `payment_method` (`cash`, `upi`, `bank_transfer`, `other`)
- `amount`
- `payment_date`
- `reference_no` (nullable)
- `recorded_by_user_id`
- `notes` (nullable)
- `status` (`recorded`, `reversed`)
- `created_at`
- `updated_at`

#### `payouts`

- `id`
- `owner_id`
- `auction_result_id`
- `subscriber_id`
- `membership_id`
- `gross_amount`
- `deductions_amount`
- `net_amount`
- `payout_method`
- `payout_date` (nullable)
- `reference_no` (nullable)
- `status` (`pending`, `paid`, `cancelled`)
- `created_at`
- `updated_at`

#### `ledger_entries`

- `id`
- `owner_id`
- `entry_date`
- `entry_type` (`payment`, `payout`, `penalty`, `dividend`, `adjustment`)
- `source_table`
- `source_id`
- `subscriber_id` (nullable)
- `group_id` (nullable)
- `debit_amount`
- `credit_amount`
- `description`
- `created_at`

### External Tracking Domain

#### `external_chits`

- `id`
- `subscriber_id`
- `title`
- `organizer_name`
- `chit_value`
- `installment_amount`
- `cycle_frequency`
- `start_date`
- `end_date` (nullable)
- `status` (`active`, `completed`, `stopped`)
- `notes` (nullable)
- `created_at`
- `updated_at`

#### `external_chit_entries`

- `id`
- `external_chit_id`
- `entry_type` (`due`, `paid`, `won`, `penalty`, `note`)
- `entry_date`
- `amount` (nullable)
- `description`
- `created_at`

### Support Tables

#### `notifications`

- `id`
- `user_id`
- `owner_id` (nullable)
- `channel` (`in_app`, `sms`, `email`)
- `title`
- `message`
- `status` (`pending`, `sent`, `failed`, `read`)
- `created_at`
- `sent_at` (nullable)

#### `audit_logs`

- `id`
- `actor_user_id` (nullable)
- `owner_id` (nullable)
- `action`
- `entity_type`
- `entity_id`
- `metadata_json`
- `created_at`

## Business Rules

1. Every managed chit group belongs to exactly one `chit_owner`.
2. A subscriber can join multiple managed groups under the same owner.
3. A chit owner can also participate in a managed group if they have a linked subscriber profile.
4. Any user with a subscriber profile can maintain private `external_chits`.
5. External chits are strictly personal tracking records and never enter live bidding or shared payout workflows.
6. Only active, eligible, unprized memberships can bid in an open auction session.
7. Auction result finalization must update the result, the winning membership state, and payout draft creation atomically.
8. Payments and payouts must create ledger entries.
9. Bids, results, payments, payouts, and audit records must not be hard-deleted.

## Core Workflows

### Owner Setup

1. Super admin creates or activates a chit owner account.
2. Chit owner signs in.
3. Chit owner optionally activates a linked subscriber profile.

### Subscriber Onboarding

1. Chit owner adds a subscriber under their workspace.
2. Subscriber account is activated.
3. Subscriber signs in and views managed memberships and optional private external chits.

### Group Creation

1. Chit owner creates a group.
2. Group starts in `draft`.
3. Members are assigned.
4. Installment schedules and auction cycles are generated.
5. Group becomes `active`.

### Payment Posting

1. Subscriber pays or owner records the payment.
2. The payment is linked to the membership and installment where applicable.
3. Installment balances are updated.
4. Ledger entries are created.

### Live Auction

1. Owner opens the auction session.
2. Eligible members enter the room.
3. Subscribers place bids online.
4. Backend validates timing, eligibility, and amount rules.
5. Owner or server closes the session.
6. Backend computes the winner.
7. Result is finalized and payout draft is created.

### External Chit Tracking

1. Subscriber creates an external chit.
2. Subscriber records due, paid, won, penalty, or note entries.
3. The external chit remains private to that subscriber profile.

## Fast Auction Architecture

### Hot Path Principles

Auction traffic must remain lightweight and deterministic.

The bid endpoint should only:

1. authenticate
2. validate session state
3. validate membership ownership and eligibility
4. validate the bid amount
5. persist the bid
6. update lightweight cached room state
7. publish a realtime event

It must not run expensive notifications, reporting, statement generation, or large recalculations inline.

### Realtime Model

Use websocket-driven room updates for:

1. session open
2. countdown synchronization
3. bid accepted or rejected
4. current leader indicator or privacy-safe equivalent
5. session closed
6. result published

### Redis Responsibilities

Redis should be used for:

1. active room state
2. presence tracking
3. lightweight latest-bid snapshots
4. rate limiting
5. short-lived locks for close and finalize
6. websocket fanout

### Auction Finalization

Close and finalize must be lock-protected and idempotent:

1. acquire lock
2. mark session closed
3. reject further bids
4. fetch valid bids
5. compute winner deterministically
6. persist result
7. update winning membership state
8. create payout draft
9. publish result event
10. release lock

## API Boundaries

### Hot Path Endpoints

1. `GET /api/auctions/{session_id}/room`
2. `POST /api/auctions/{session_id}/bids`
3. `POST /api/auctions/{session_id}/open`
4. `POST /api/auctions/{session_id}/close`
5. `POST /api/auctions/{session_id}/finalize`
6. `GET /api/auctions/{session_id}/result`

### Management Endpoints

1. auth
2. owners
3. subscribers
4. groups
5. memberships
6. installments
7. payments
8. payouts
9. external chit records
10. notifications
11. audit

Write paths for bids, payments, and close/finalize flows should accept idempotency keys where appropriate.

## Frontend Structure

### Product Surfaces

1. super-admin dashboard
2. chit-owner dashboard
3. subscriber portal

### Subscriber Experience

Any user with a subscriber profile should see:

1. `My Managed Chits`
2. `My External Chits`

If a chit owner also has a subscriber profile, the same account should expose:

1. `Owner Dashboard`
2. `My Managed Chits`
3. `My External Chits`

### Auction UI

The auction room must be isolated from heavy dashboard screens. It should:

1. load a lean initial room payload
2. open websocket connection immediately
3. keep local room state small
4. avoid whole-page refetches during bidding
5. show only essential auction information

## Indexing and Performance

At minimum, add indexes for:

1. `auction_sessions(group_id, cycle_no)`
2. `auction_sessions(status, scheduled_start_at)`
3. `auction_bids(auction_session_id, placed_at)`
4. `auction_bids(auction_session_id, membership_id, is_valid)`
5. `group_memberships(group_id, subscriber_id)`
6. `group_memberships(group_id, membership_status, prized_status, can_bid)`
7. `installments(membership_id, cycle_no)`
8. `installments(membership_id, status)`

Operational target:

1. fast bid acceptance
2. near-realtime room updates
3. deterministic close/finalize within seconds
4. no report or notification work on the auction hot path

## Security and Integrity

The main integrity risks are unauthorized bidding, duplicate submissions, late bids, and inconsistent finalization.

Required protections:

1. server-authoritative timestamps
2. idempotency keys on sensitive writes
3. lock-protected close/finalize
4. immutable accepted bids
5. explicit tie-break and winner computation rules
6. audit logs for open, bid, close, finalize, payout, and reversal actions

When a chit owner participates as a subscriber, their bid must go through the exact same participant validation path as any other subscriber.

## Observability and Operations

Track these hot-path metrics:

1. bid latency
2. websocket publish latency
3. participant count per session
4. rejected bids by reason
5. close-to-result latency
6. Redis latency
7. database timings for auction queries
8. websocket disconnect rates

The deployment should support:

1. stateless backend instances
2. shared PostgreSQL and Redis
3. UTC server time everywhere
4. separate worker execution for non-critical work
5. safe recovery from reconnects and retried finalization

## Out of Scope for This Version

1. KYC verification workflows
2. branch hierarchies
3. agent role
4. enterprise multi-tenant organization trees
5. external chit live auctions
6. heavy accounting modules beyond practical ledger entries for payments and payouts
