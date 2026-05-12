## To a Tech Lead
You are architecting a cross-chain, event-driven ETL and inference pipeline designed to calculate token-weighted governance probabilities. 

The system bypasses standard financial modeling in favor of identity resolution and state tracking. The ingestion layer runs on Python and AWS, utilizing jittered, stateful REST polling to scrape unstructured social sentiment (Discord) while evading anti-bot heuristics. This unstructured text is passed through an LLM for discrete stance classification (YES/NO/NEUTRAL). Simultaneously, the pipeline queries UMA disputes and DVM Ethereum outcomes to understand how votes voted in a dispute.

The core processing layer executes an inner join on these datasets, multiplying the LLM-derived social stance by the on-chain voting weight of the identified entities. This result is then displayed on a live dashboard updated every 5 minutes.


## To a Business Investor / Stakeholder
The objective is to exploit a structural inefficiency and capital mismatch in decentralized prediction markets, specifically Polymarket. 

Retail participants on Polymarket trade based on real-world facts. However, disputed markets are not resolved by facts; they are resolved by a token-weighted governance vote via the UMA protocol. This creates a severe mispricing. The engine we are building programmatically tracks the social coordination and financial exposure of the specific whales who control the UMA voting supply. 

By mapping their off-chain discussions to their on-chain voting power, we generate a proprietary, subjective probability (tau) of the final resolution. When our projected outcome violently diverges from the retail-driven market price, we execute a low-frequency, highly asymmetric discretionary trade. Because the UMA token market cap is significantly smaller than Polymarket's Total Value Locked, oracle manipulation is *probable*. Our system is designed to front-run that manipulation. The strategy offers an uncorrelated edge that has a *roughly even chance* of remaining unexploited by high-frequency firms due to the messy, unstructured nature of the underlying data.

## To a Potential User
This dashboard indicates when a prediction market dispute is *almost certainly* going to flip against the consensus.

When a Polymarket event is disputed, reading the news or arguing about the truth is useless. The only thing that matters is how the UMA token holders will vote. This system tracks the exact individuals holding the voting power, reads their public chat logs, and calculates their intended vote based on their wallet size. 

If the public market is pricing a "YES" resolution at 80 cents, but the dashboard shows that the whales controlling 60% of the voting tokens are actively organizing to vote "NO," you have a measurable edge. The board visualizes the gap between what the crowd believes is true and what the token holders are *highly likely* going to enforce. It allows you to buy the undervalued side of a dispute before the decentralized vote actually executes.