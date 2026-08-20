This describes how the frontend for users should look like.

Data should be mocked first, before the backend API is fully developed. Most of the data should follow existing dev UI requirements.

# OVERVIEW

- Single page React.js application
- 3 tabs to load

# tab1: main dashboard

this is where the user will be shown a screener front and center.

the screener has a table which shows for each market:

- market_id
- question
- link to polymarket market page `(https://polymarket.com/market/<slug>)`
- market_status (live_dispute, dispute_resolved_closed (can be P1, P2, P3), dispute_too_early (P4) ) --> since the onyl markets we have in the database are those that have been raised to dispute at least once.
- latest_dispute_started time
- market_closed_time (can be N/A for markets too_early or in live_dispute)
- market_specified_end_time (when the market is supposed ot end when it was first created)
- YES price (0.XX) (GREEN)
- NO price (0.XX) (RED)
- # of voters in discord
- predominant vote (% of total) `YES|NO|UNKNOWN|EARLY (XX %)`

The table should automatically highlight rows in a accent colour where the market is in LIVE DISPUTE.

the table itself can be sorted by any of the columns by the user, however the DEFAULT settings are:

- sort by latest_dispute_started

toggles:
the user can toggle these filters to change the results in the table

- Show markets with LIVE DISPUTES only (this is typically a low number of rows.)

- A slider filter that excludes markets where the latest dispute rounds have <> N number of voters

# user action

the main user action is when they click on a specific row (STATS or CHARTS icon) in the screener table. this icon should be on the left of each market_id for conveneince.

this draws up a panel (ANALYSIS panel) from the bottom of the screen to take over the main page.

the screener itself gets vertically minimized towards the top of the screen, with an arrow down button that will undo the panel that just appeared and return back to the screener screen.

!note: i may want to switch this to a sliding panel from the right instead, lets see how the UI looks first...

## dispute analysis panel

the panel has 4 sections:

1. headlines

- question: Will xxx...??
- status pill: [LIVE DISPUTE] [RESOLVED P#] [RESOLVED EARLY]
- YES | NO price [real-time] * use gamma api to pull for this market
- voter predominant consensus: 
- if this is a non-EARLY resolved dispute: show the maximum observed CONSENSUS_PRICE_DELTA (+0.XXc | -0.XXc) @ timestamp, that was observed during the dispute period.
- if this is a LIVE DISPUTE: 
-- show the current CONSENSUS_PRICE_DELTA (+0.XXc | -0.XXc)
-- show the ORDER_BOOK which is just from the gamma API: show best bid($0.XX #shares) /ask ($0.XX #shares)

the next 2 sections are full page tabs

TAB A. market info

- side by side KEY_INFO panel and PRICE_CHART panel

KEY_INFO:
- market description
- resolution sources (link)
- number of times disputed (rounds)

PRICE_CHART
- stepped line chart of YES price
- mousing over should show the price, timestamp pair as data callouts
- latest dispute round (time range) should be highlighted region

TAB B. dispute info

TOP:
overall dispute metrics

VOTER_DISTRIBUTION_CHART:

- this is a point in time snapshot (latest time)
- as of the latest time, shows 4 lanes (P1 - 4)
- for each lane, plots 1 dot per unique user vote (we only take the LATEST vote per user)
- the y-axis position of the dot corresponds to the user's bayesian accuracy score considering their history up until that point. (point-in-time)
- for each lane, draw the average line (RMS/ power-mean) 
- draw a threshold line to show the minimum bayesian accuracy that is configured from settings. any users which come in below this value should still be plotted but as a grey circle to indicate that their votes have been excluded due to poor user reliability. (note that this means the data aggregatino still needs to pull ALL user votes, but needs to label the low scoring votes so that they can be used for this section) 
- on the same chart, plot bar chart for each lane that shows the consensus share % (after weighting)

BOTTOM:
side by side panel of CHART (70% width) and REPLAY_LOG (30% width)

VOTER_CONSENSUS_CHART:

- this shows the change over time of the consensus share %.
- time range only shows the dispute timerange
- stepped line chart
- thin line in background for YES price
- mousing over should show the P1,2,3,4 (if appplicable) consensus share %, and YES price, timestamp pair as data callouts
- mousing over should also LINK to the next chart...

DISPUTE_THREAD_REPLAY:
- twitch/ youtube - like chat stream where the messages are messages in the discord thread by timestamp
- when mousing over the chart,  e.g. moving left to right, it should auto 'scroll' the chat stream and highlight the closest message that was posted at that point of time.
- chat stream should render the message in the replay. no need to render images. links can be hyperlinked if needed.
- chat stream should show a simple <user_name>: <message> like youtube stream chats. truncate `...` if its too long, and allow for a `->` expand 




# general rules
all timelines/ stamps should show in DD MMM YYYY format. for axis charts, DD MMM is sufficient.

time should be reflected in UTC, and HH:MM:SS







# global settings

since a lot of the calculations are based on some constants, we want these constants to be applicable to the entire application while being configurable.

the settings should be accessible by a gear icon at the top right and opens up a modal:

## discord noise filter
only considers user messages/votes from users where:

- minimum experience: voter has >= N votes in their history (default = 10) range = 3-100

- minimum competency: voter's bayesian accuracy is > X % (default = 50%, i.e. only count people who are better than random guessing) range = 0 - 80%

## bayesian accuracy parameters
how much weight do we give to more experienced vs less experienced voters?

- trust number: default=20 (range = 10 --> 50)
- prior_score: 0.50 (all new voters are assumed to be no better than random guessing) (range = 0.2 --> 0.8)
- weighting method: S^2 to penalise lower accuracy voters more heavily. this is fixed for consistent caluclaitons in other sections of the app.


# backend calculations

the backend will deliver the post-calculated values in JSON format for the frontend to display. hence there should be no need for frontend to do any calculations.

all data is pulled from backedn through the following APIs:

GET /api/screen
- ... URL params required to fulfill the database pull and deliver the data in tabular filtered osrted format

GET /api/market?id=...
> this handles all data loading for the entire TAB A/ TAB B panels.
- and extra URL options to perform the required calculations from the datawarehouse.

- this call may also need to reach out to LIVE polymarket gamma api to get the latest pricing, but this should be instant.

some important URL params are the settings that are persisted from the SETTINGS section, if no settings are changed, then the default values can be passed.

