# Individual reflection: BE-01 Digital Banking Core Platform

## What I owned
I took this project from the brief to a running system on my own laptop. I set up the full toolchain on Windows (Git Bash, JDK 21, Maven, a container engine), got PostgreSQL, Kafka and Keycloak running from `docker-compose.yml`, and ran the 32 integration tests until they all passed. I debugged the environment problems myself: Maven running on the wrong JDK, Docker not working for Testcontainers so I switched to Podman, and a port clash with another PostgreSQL that made the application fail to log in. I recorded the presentation and live demo video, wrote the reflection, organised the GitHub repository for submission and cleaned the commit history so every commit carries my own name. I also took responsibility for understanding the design well enough to explain it: the ledger, the transfer transaction, idempotency, locking, the outbox and the fraud rules.

## What I learned
- **Double-entry bookkeeping.** Money is never just added or subtracted. Every movement is a debit and a credit that sum to zero, so the whole bank must always sum to zero. That makes a reconciliation check meaningful.
- **Let the database enforce the rules.** A deferred constraint trigger rejects an unbalanced transaction at commit and an append-only trigger blocks edits to history. Even a bug in the Java code cannot unbalance the books.
- **Atomicity and idempotency belong in the same transaction.** Storing the idempotency key together with the money movement means the key exists if and only if the transfer committed, so a retry can never double-charge.
- **Concurrency is about lock order.** Locking both accounts with `FOR NO KEY UPDATE`, always in ascending id, prevents lost updates and deadlocks between A to B and B to A transfers.
- **The transactional outbox.** A database and Kafka cannot share a transaction, so the event is written to a table inside the money transaction and published afterwards. Consumers must then be idempotent because delivery is at-least-once.
- **Security is more than a login.** Role checks decide what you may call, but object-level checks decide whose data you may see. Returning 404 for someone else's account avoids revealing that it exists.
- **Testing against the real thing matters.** Testcontainers with a real PostgreSQL caught what a mock would hide, and parallel tests with a start gate made real contention.

## Hardest problem and how I handled it
Getting the project to run on my machine took longer than expected, and it taught me to read errors carefully. Maven reported `release version 21 not supported` because it was running on an older JDK, so I had to point `JAVA_HOME` at JDK 21 and verify with `mvn --version`. Then the tests failed with `Could not find a valid Docker environment`; I switched to Podman and all 32 tests passed. Finally the application failed with a password authentication error. The cause was another PostgreSQL already using port 5433, so my app was talking to the wrong database. Mapping the container to a different host port and passing `DB_URL` fixed it. Each time the lesson was the same: check which process is really answering before changing the code.

## What I would do next
- Shard the single cash clearing account per branch so cash operations are not serialised.
- Add reversals and refunds as correcting ledger entries.
- Support more than one currency, with FX rates and a conversion account.
- Replace static fraud thresholds with a scoring model.
- Move to the authorization-code flow with PKCE, real secrets and TLS, and upgrade to Spring Boot 4.
- Measure real throughput of the Spring application, not just the SQL replay.
