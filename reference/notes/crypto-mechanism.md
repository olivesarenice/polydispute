# Why we only care about DVM's revealed vots:

OK.

The difference between a committed vote and a revealed vote stems from the cryptographic design of the UMA Data Verification Mechanism (DVM). UMA utilizes a two-phase "commit-reveal" scheme to prevent voter collusion, bribery, and herd mentality.



### 1. The Commit Phase (`committedVotes`)
During the first phase of a DVM vote, token holders review the dispute and decide on an outcome. However, if they voted publicly, late voters would simply copy the current majority to guarantee a payout. 

To prevent this, voters combine their chosen answer (the `price`), their Ethereum address, and a randomly generated secret password (a "salt"). They hash this combined data and submit only the resulting hash to the blockchain. 

* **What the contract knows:** The voter's identity and their token weight (`numTokens`).
* **What the contract does not know:** The actual answer they chose.

### 2. The Reveal Phase (`revealedVotes`)
During the subsequent phase, voters must return and submit a second transaction. This transaction contains their plaintext answer and their secret salt. The smart contract hashes these inputs on-chain. If the resulting hash perfectly matches the hash submitted during the Commit Phase, the vote is officially unlocked and counted.

---

### Why the Data in the Two Groups Differs

When you query the GraphQL subgraph and compare the `committedVotes` array to the `revealedVotes` array, it is almost certain you will find discrepancies. This occurs for two technical reasons:

* **Voter Attrition (Failure to Reveal):** It is highly likely that the total number of committed votes will be greater than the number of revealed votes. If a user commits a vote but fails to execute the second transaction before the reveal window expires, their vote is excluded from the final tally. The subgraph records a `CommittedVote` entity, but a corresponding `RevealedVote` entity is never generated.
* **Schema Asymmetry:** Because of the cryptographic hiding, the data fields physically available to the indexer differ between the two phases. A `CommittedVote` object in the UMA subgraph lacks the `price` field (the Yes/No/Unknown outcome) because that data remains encrypted on-chain. The `price` field, and the specific `VoterGroup` the user belongs to, only materialize within the `RevealedVote` object.