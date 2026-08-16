## SRE / Reliability Targets

### Golden Signals

- **Latency:** P95/P99 latency for URL redirects and URL creation
- **Traffic:** Requests/sec, redirects/sec and URL creation rate
- **Errors:** 4xx/5xx responses, failed URL creation and dependency failures
- **Saturation:** DynamoDB throttling, Redis utilization and application resource usage

## SLOs, Error Budgets & Priorities

| Service Objective | SLO Target | Error Budget | Consequence if Violated | Priority |
|---|---:|---:|---|:---:|
| Redirect Availability | 99.99% | 0.01% (~4.32 min/month) | Users may not be able to open the shortened links. This directly impacts the main service functionality. | P1 |
| URL Creation Availability | 99.9% | 0.1% (~43.2 min/month) | Users may not be able to create new shortened links. Existing links can still work. | P2 |
| Redirect P95 Latency | < 100 ms | 5% of requests may exceed target | Users may experience slow redirection, especially during high traffic. | P2 |
| Redirect P99 Latency | < 250 ms | 1% of requests may exceed target | A small number of users may experience significantly slow redirects during peak traffic. | P2 |
| 5xx Error Rate | < 0.1% | 0.1% | Users may see server errors while creating or accessing shortened links. | P1 |
| DynamoDB Throttling | No sustained throttling | Minimal | URL creation or redirection may become slow or fail when the database cannot handle the traffic. | P1 |
| Redis Availability | 99.9%+ | 0.1% | Redirects can still work through DynamoDB, but users may experience higher redirect latency during cache failures. | P3 |

## Note
- We prioritize SLOs based on user impact. If redirects fail, that's P1 because the core purpose of the service is affected. 
- If redirects are only slow or URL creation is impacted, that's P2. 
- Dependency issues such as Redis being unavailable can be P3 when the system has a fallback and users can still use the service.
