"""
Polymarket Active Markets Puller (v2 - Events API) — NO PANDAS VERSION
======================================================================
Same as polymarket_pull.py but uses only stdlib + requests.
Needed because Windows Application Control is blocking numpy DLLs.

SETUP (one-time):
    pip install requests

USAGE:
    python polymarket_pull_nopandas.py
"""

import requests
from datetime import datetime
import time
import sys
import re
import json
import csv
from collections import Counter

print("=" * 60)
print("POLYMARKET PULLER v2 — EVENTS API (no-pandas)")
print("=" * 60)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
EVENTS_ENDPOINT = f"{GAMMA_API_BASE}/events"
PAGE_SIZE = 100

FILTERS = {
    "closed": "false",
    "order": "volume",
    "ascending": "false",
    "limit": PAGE_SIZE,
}

MAX_EVENTS = None
MIN_LIQUIDITY = 1000
MIN_VOLUME = 5000
EXCLUDED_KEYWORDS = []

CATEGORY_RULES = [
    # Crypto first — any market matching these is dropped in filter_excluded().
    # User policy: never surface crypto contracts in CSVs, dashboards, or briefings.
    ("Crypto", [
        r"\b(bitcoin|btc|ethereum|eth|crypto|cryptocurrency|altcoin|stablecoin|stable coin)\b",
        r"\b(solana|sol|cardano|ada|polkadot|dot|dogecoin|doge|shiba|shib|xrp|ripple)\b",
        r"\b(coinbase|binance|kraken|gemini exchange|crypto exchange)\b",
        r"\b(defi|nft|web3|memecoin|meme coin|pepe coin|pepecoin)\b",
        r"\b(usdt|usdc|tether)\b",
        # Crypto-launch lingo: tokens, FDV, mainnet, airdrops — these phrases are
        # near-exclusively used in crypto contexts.
        r"\b(fdv|fully diluted|mainnet launch|token launch|token unlock|airdrop)\b",
        r"\b(market cap above \$\d|fdv above \$\d)\b",
        # Per user policy: anything mentioning "token" is crypto.
        r"\btokens?\b",
        # Other crypto-specific terminology
        r"\b(blockchain|on.chain|smart contract|dao|layer 2|l2 rollup|rollup|tvl|staking|validator)\b",
        r"\b(hyperliquid|aerodrome|jupiter exchange|uniswap|aave|compound finance|maker dao|lido|pendle|ondo)\b",
        r"\b(trump coin|trump meme|melania coin|libra coin|world liberty financial|wlfi)\b",
    ]),
    # Esports separated out from Sports — listed first so esports keywords win.
    ("Esports", [
        r"\besports?\b",
        r"\b(lpl|lcs|lec|lck|league of legends|lol world|worlds \d{4})\b",
        r"\b(dota ?2?|the international|valorant|champions tour|vct)\b",
        r"\b(counter.strike|cs ?go|cs ?2|major counter|esl pro league|blast premier|iem katowice)\b",
        r"\b(overwatch league|owl|call of duty league|cdl|apex legends als|rocket league rlcs)\b",
        r"\bBO3\b|\bBO5\b",
        r"\b(ESL|HEROIC|Lilmix|t1 esports|fnatic|cloud9|nrg esports|natus vincere|navi|g2 esports|team liquid|faze clan|tsm esports|betboom team|thundertalk gaming|lgd gaming)\b",
    ]),
    ("Sports", [
        r"\b(nba|nfl|mlb|nhl|wnba|mls|ufc|mma|pga|nascar|ipl|epl|kbo|npb)\b",
        r"\b(basketball|football|baseball|hockey|soccer|tennis|golf|boxing|cricket|rugby)\b",
        r"\b(lakers|celtics|warriors|chiefs|eagles|cowboys|yankees|dodgers|bruins|rangers|knicks|nets|heat|bucks|suns|nuggets|clippers)\b",
        r"\b(premier league|la liga|serie a|champions league|bundesliga|wimbledon|ligue 1|eredivisie|primeira liga)\b",
        r"\b(super bowl|world series|stanley cup|march madness|olympics)\b",
        r"\b(fifa|world cup|copa america|copa libertadores|euros|euro \d{4}|afcon)\b",
        r"\b(french open|us open|australian open|atp|wta|grand slam)\b",
        r"\b(f1|formula 1|grand prix)\b",
        # Awards, league seasons — questions like "Will [X] win the
        # 2026 American League MVP"
        r"\b(mvp|cy young|heisman|ballon d'?or|golden boot|rookie of the year)\b",
        r"\b(american league|national league|al east|al west|nl east|nl west)\b",
        # Top European soccer clubs — these often appear in vs. markets without any
        # league keyword. Common naming variants included.
        r"\b(real madrid|barcelona|barca|espanyol|atletico madrid|sevilla|valencia|villarreal|real sociedad|athletic bilbao|girona)\b",
        r"\b(manchester united|man united|man utd|manchester city|man city|liverpool|arsenal|chelsea|tottenham|spurs|newcastle|aston villa|west ham)\b",
        r"\b(psg|paris saint.germain|marseille|lyon|monaco|lens|lille)\b",
        r"\b(bayern munich|bayern|borussia dortmund|dortmund|leipzig|leverkusen|bayer leverkusen)\b",
        r"\b(juventus|juve|ac milan|inter milan|inter|napoli|roma|lazio|atalanta|fiorentina)\b",
        r"\b(ajax|psv|feyenoord|porto|benfica|sporting cp|celtic|rangers)\b",
        # MLS clubs
        r"\b(nycfc|new york city fc|lafc|los angeles fc|inter miami|atlanta united|seattle sounders|la galaxy|portland timbers|toronto fc|nashville sc|orlando city|columbus crew|cincinnati fc)\b",
        # Generic match-outcome patterns: any "X vs. Y" market with soccer-specific
        # terminology like draw / penalties / extra time / halftime
        r"\bvs\.?\s+\w+\s+(end in a draw|go to penalties|in extra time|at halftime|first half|second half)\b",
        # Olympic medal markets are sports
        r"\b(olympic medal|paralympic|olympic gold|olympic silver|olympic bronze)\b",
        # Golf majors and golf players
        r"\b(masters tournament|the masters|pga championship|the open championship|us open golf|ryder cup|presidents cup|liv golf)\b",
        r"\b(scottie scheffler|rory mcilroy|jon rahm|bryson dechambeau|xander schauffele|viktor hovland|justin thomas|jordan spieth|tiger woods|brooks koepka)\b",
        # F1 drivers and teams (in addition to f1/grand prix already)
        r"\b(max verstappen|lewis hamilton|lando norris|charles leclerc|oscar piastri|george russell|carlos sainz|fernando alonso|sergio perez|pierre gasly)\b",
        r"\b(red bull racing|mercedes f1|ferrari f1|mclaren f1|aston martin f1|alpine f1|williams racing)\b",
        # Tennis players (ATP/WTA already there but names help with single-mention markets)
        r"\b(carlos alcaraz|jannik sinner|novak djokovic|rafael nadal|daniil medvedev|alexander zverev|andrey rublev|stefanos tsitsipas|holger rune|joao fonseca|lorenzo musetti)\b",
        r"\b(iga swiatek|aryna sabalenka|coco gauff|elena rybakina|jessica pegula|emma raducanu|naomi osaka)\b",
        # NBA / NFL / MLB superstars by name
        r"\b(lebron james|stephen curry|steph curry|kevin durant|giannis|luka doncic|joel embiid|nikola jokic|jayson tatum|anthony edwards|victor wembanyama|wemby)\b",
        r"\b(patrick mahomes|josh allen|jalen hurts|joe burrow|lamar jackson|aaron rodgers|trevor lawrence|caleb williams|tom brady)\b",
        r"\b(shohei ohtani|aaron judge|ronald acuna|juan soto|mike trout|julio rodriguez|bobby witt|paul skenes|mookie betts|freddie freeman)\b",
        r"\b(connor mcdavid|leon draisaitl|nathan mackinnon|auston matthews|sidney crosby|alex ovechkin)\b",
        # Boxing & MMA fighters
        r"\b(canelo alvarez|tyson fury|oleksandr usyk|anthony joshua|jake paul|logan paul fight|conor mcgregor|jon jones|israel adesanya|alex pereira|sean strickland|dustin poirier)\b",
        # Horse racing & motorsports
        r"\b(kentucky derby|preakness|belmont stakes|triple crown|breeders cup|royal ascot|melbourne cup)\b",
        r"\b(indycar|moto ?gp|world rally|le mans|daytona 500)\b",
        # Cricket events (IPL already covered)
        r"\b(t20 world cup|odi world cup|champions trophy|the ashes|big bash|psl|bbl|ranji trophy)\b",
        # Generic match outcome words
        r"\b(starting lineup|coach fired|head coach hired|manager fired|trade deadline|draft pick|rookie draft)\b",
    ]),
    ("Earnings", [
        r"\bearnings\b", r"\brevenue\b", r"\bEPS\b", r"\bquarterly results\b",
        r"\bearnings call\b", r"\bbeat estimates\b", r"\bmiss estimates\b",
        r"\bfiscal quarter\b", r"\b10-[kq]\b", r"\bannual report\b",
    ]),
    ("AI/Tech", [
        r"\b(ai|artificial intelligence|openai|anthropic|deepmind|gpt|chatgpt|gemini|claude)\b",
        # More AI labs and chatbots
        r"\b(mistral ai|mistral|x ?ai|grok|perplexity|cohere|inflection ai|stability ai|midjourney|runway ml|character ai|hugging face|llama|meta ai)\b",
        r"\b(tech|silicon valley|apple|google|alphabet|microsoft|meta|nvidia|tesla|amazon|netflix|oracle|salesforce|adobe|intel|amd|tsmc|asml|broadcom|qualcomm|arm holdings)\b",
        r"\b(elon musk|elon|musk|spacex|x \(twitter\)|twitter|neuralink|starlink|the boring company|xai)\b",
        r"\b(agi|llm|machine learning|robotics|semiconductor|chip|self.driving|autonomous|humanoid robot|optimus)\b",
        # Tech CEOs and founders by name
        r"\b(jensen huang|sundar pichai|tim cook|sam altman|mark zuckerberg|zuck|andy jassy|satya nadella|sergey brin|larry page|bill gates|jeff bezos|dario amodei|demis hassabis|lisa su|pat gelsinger)\b",
        # Tech companies often referenced without parent brand
        r"\b(waymo|cruise|uber|lyft|airbnb|stripe|palantir|snowflake|databricks|rivian|lucid|robinhood|reddit|pinterest|snap inc|figma|notion|asana|atlassian)\b",
        # Apple products and major launches
        r"\b(iphone|ipad|macbook|apple watch|vision pro|airpods|app store)\b",
        # Space exploration — typically tech/innovation adjacent
        r"\b(nasa|artemis|moon mission|moon landing|mars mission|mars colony|space station|iss|starship|james webb|jwst)\b",
    ]),
    ("Entertainment", [
        r"\b(netflix|disney|hbo|hulu|paramount|peacock|max streaming|spotify|youtube|tiktok|instagram|snapchat|threads)\b",
        r"\b(movie|film|oscar|academy award|grammy|emmy|tony|golden globe|box office|james bond|next bond|sag award|bafta|cannes|sundance|tribeca)\b",
        # season \d+ (not just \d) so "season 22" matches; bachelor/bachelorette explicit
        r"\b(album|song|concert|tour|streaming|show|season \d+|reality tv|bachelor|bachelorette|love island|survivor|big brother|drag race|the voice|american idol|dancing with the stars)\b",
        r"\b(celebrity|kardashian|jenner|taylor swift|travis kelce|drake|beyonce|rihanna|ariana grande|billie eilish|olivia rodrigo|sabrina carpenter|chappell roan)\b",
        # Podcasters / streamers / influencers
        r"\b(joe rogan|theo von|lex fridman|ben shapiro show|tucker carlson show|kai cenat|ishowspeed|kick streamer|twitch streamer|mrbeast|mr beast|pewdiepie|logan paul|ksi|jake paul|andrew tate|hasan piker)\b",
        # Video games and gaming events
        r"\b(gta\s?vi|grand theft auto|elder scrolls|witcher|cyberpunk|minecraft|fortnite|roblox|league of legends worlds|the game awards|video game release|game release)\b",
        # Music charts and album/single releases
        r"\b(billboard hot 100|billboard 200|number one single|debut album|new album|chart.topping)\b",
        # Music festivals and major concerts
        r"\b(eurovision|song contest|music festival|glastonbury|coachella|bonnaroo|lollapalooza|reading festival|leeds festival|rock in rio|fuji rock)\b",
        r"\b(grammy awards|brit awards|american music awards|mtv vma|live aid|woodstock|burning man)\b",
        r"\btop US Netflix\b",
    ]),
    ("Religion", [
        r"\b(jesus|christ|second coming|messiah|biblical)\b",
        r"\b(pope|vatican|cardinal|papal|conclave|holy see)\b",
        r"\b(islam|muslim|christianity|christian|judaism|jewish|hindu|buddhist|catholic|protestant|evangelical)\b",
    ]),
    ("Health", [
        # Pandemics, outbreaks, named diseases
        r"\b(pandemic|epidemic|outbreak|public health emergency)\b",
        r"\b(covid|covid.19|sars|mers|coronavirus|flu season|influenza|h5n1|bird flu|avian flu|swine flu)\b",
        r"\b(mpox|monkeypox|ebola|marburg|zika|dengue|cholera|tuberculosis|measles|polio)\b",
        # Drugs, vaccines, regulators
        r"\b(vaccine|booster shot|fda approval|cdc|who director|world health organization|nih|hhs)\b",
        r"\b(ozempic|wegovy|mounjaro|glp.?1|semaglutide|tirzepatide|alzheimer'?s drug)\b",
        # Generic medical / mortality
        r"\b(life expectancy|cancer cure|gene therapy|mrna|crispr|biotech)\b",
    ]),
    ("Weather", [
        # Weather proper
        r"\b(hurricane|tornado|typhoon|cyclone|tropical storm)\b",
        r"\b(temperature|hottest|coldest|warmest|coolest|heat wave|cold snap)\b",
        r"\b(snow|snowfall|rainfall|precipitation|blizzard)\b",
        r"\b(wildfire|drought|flood|flooding)\b",
        r"\b(climate change|global warming|el ni[ñn]o|la ni[ñn]a)\b",
        r"\b(\d+(st|nd|rd|th) (hottest|coldest|warmest) (on record|month|year))\b",
        r"\b(noaa|nws|hurricane center)\b",
        # Natural disasters / geological events grouped here so they don't fall to Other
        r"\b(volcano|volcanic|eruption|erupts?)\b",
        r"\b(earthquake|magnitude \d|richter scale|seismic)\b",
        r"\b(tsunami|landslide|mudslide|sinkhole)\b",
        r"\bvei\s?\d\b",  # Volcanic Explosivity Index — e.g. "VEI 4"
        r"\b(asteroid|meteor|near.earth object)\b",
    ]),
    ("Legal/Crime", [
        r"\b(court|judge|ruling|lawsuit|indictment|convicted|sentenced|charged|verdict)\b",
        r"\b(supreme court|scotus|trial|prosecution|plea|prison|jail)\b",
        r"\b(shooter|shooting|murder|crime|arrest|fbi)\b",
        r"\b(extradite|pardon|clemency)\b",
        r"\b(epstein|epstein'?s island|diddy|sean combs|p.?diddy|cosby)\b",
    ]),
    ("Finance", [
        # M&A, acquisitions, mergers, IPOs
        r"\b(acquire|acquisition|acquired|merger|merged|ipo|initial public offering|go public|buyout|takeover)\b",
        r"\b(be acquired|will.*acquire|will.*merge|announced.*acquisition|announced.*merger|will.*go public)\b",
        # Specific acquisition/merger patterns
        r"\b(will .* (acquire|acquire|buy|merge with))\b",
        # IPO related
        r"\b(ipo|direct listing|spac merger|blank check company)\b",
        # Private equity and financial transactions
        r"\b(leveraged buyout|lbo|private equity|pe firm|buyback|share repurchase)\b",
        # Bankruptcy and financial distress
        r"\b(bankruptcy|insolvency|bail.?out|bank run|bank fail|fdic|bankrupt)\b",
    ]),
    ("Economics", [
        # Macroeconomic indicators
        r"\b(fed|federal reserve|interest rate|inflation|gdp|recession|unemployment)\b",
        r"\b(tariff|trade war|sanctions|treasury|debt ceiling|deficit)\b",
        r"\b(bank of japan|ecb|central bank|monetary policy)\b",
        # Employment and labor
        r"\b(jobs report|nonfarm payrolls|unemployment rate|job creation|labor force)\b",
        # Market indices and broad financial indicators
        r"\b(s&p 500|dow jones|nasdaq|stock market|bear market|bull market)\b",
        r"\b(cpi|ppi|consumer prices|producer prices|wage growth)\b",
        # Commodities and physical assets
        r"\b(oil price|commodity|housing market|real estate|home prices)\b",
        # Commodities by name & ticker — Silver (SI), Gold (GC), Copper (HG), WTI, Brent
        r"\b(silver|gold|platinum|palladium|copper|wti|brent|natural gas)\b",
        r"\(SI\)|\(GC\)|\(HG\)|\(CL\)|\(NG\)",
        # Energy markets — oil, gas, renewables
        r"\b(oil|opec|crude|petroleum|shale|fracking|drilling|refinery)\b",
        r"\b(lng|liquified natural gas|energy prices|energy sector|energy stocks|utilities)\b",
        r"\b(renewable energy|solar|wind|hydro|nuclear power|hydroelectric)\b",
        r"\b(energy crisis|power outage|energy cost|fuel price)\b",
    ]),
    ("Geopolitics", [
        r"\b(war|invasion|ceasefire|nato|military|troops|missile|nuclear|nuke)\b",
        r"\b(hamas|hezbollah|houthis|ukraine|russia|china|iran|north korea|taiwan)\b",
        r"\b(venezuela|maduro|cuba|nicaragua)\b",
        r"\b(syria|assad|yemen|lebanon|gaza|palestine|west bank|israel)\b",
        r"\b(saudi arabia|qatar|uae|egypt|libya|sudan|ethiopia)\b",
        r"\b(netanyahu|kim jong|erdogan|orban|putin)\b",
        r"\b(leader of \w+|head of state)\b",
        r"\b(embassy|diplomat|sanctions|annex|invade|greenland)\b",
        r"\b(ISIS|al.?qaeda|taliban|terrorist)\b",
        # Geopolitical chokepoints and trade routes — ship transit / blockade markets
        r"\b(strait of hormuz|suez canal|panama canal|south china sea|taiwan strait|bab.el.mandeb|bosphorus)\b",
        r"\b(ship transit|naval blockade|freedom of navigation)\b",
    ]),
    ("Politics", [
        r"\b(election|president|prime minister|governor|senator|congress|parliament|chancellor|chancellorship)\b",
        r"\b(democrat|republican|gop|ballot|campaign|candidate|caucus|primary|midterm)\b",
        # Vote patterns — more specific to exclude Eurovision voting
        r"\b(vote for|voting for|cast.*vote|election ballot|ballot measure|electoral vote)\b",
        r"\b(mayor|cabinet|impeach|resign|political|party|coalition|confirmation hearing|senate confirmation)\b",
        r"\b(trump|biden|obama|desantis|newsom|pelosi|mcconnell)\b",
        r"\b(fidesz|tisza|by-election|primary election|runoff|special election|recall election)\b",
        r"\b(tax|wealth tax|legislation|executive order|filibuster|reconciliation bill)\b",
        # Bill patterns — more specific to legislation, not commodity tariffs
        r"\b(bill passes|legislation passes|congress passes|senate passes|will.*pass.*bill|will.*pass.*legislation)\b",
        # Nobel Peace Prize markets are typically political (e.g. Xi Jinping, Charlie Kirk)
        r"\b(nobel peace prize)\b",
        # UK politicians
        r"\b(keir starmer|starmer|boris johnson|rishi sunak|nigel farage|liz truss|kemi badenoch|ed davey|reform uk)\b",
        # Other world leaders by name (Geopolitics catches them by country word; this
        # backstop catches markets that name only the leader without the country)
        r"\b(xi jinping|narendra modi|justin trudeau|pierre poilievre|mark carney|olaf scholz|friedrich merz|emmanuel macron|marine le pen|giorgia meloni|volodymyr zelensky|anthony albanese|lula da silva|javier milei|claudia sheinbaum|sanae takaichi|pedro sanchez|mette frederiksen|ulf kristersson|alexander stubb|robert fico|donald tusk|petr pavel|alexander van der bellen)\b",
        # Trump 2nd-term cabinet & inner circle
        r"\b(kash patel|pete hegseth|marco rubio|kristi noem|tulsi gabbard|howard lutnick|linda mcmahon|doug burgum|lee zeldin|sean duffy|brooke rollins|robert lighthizer|stephen miller|susie wiles|karoline leavitt|john ratcliffe|scott bessent|chris wright|mike waltz|elise stefanik|matt gaetz|pam bondi|russ vought)\b",
        # Congressional leaders / committee chairs / notable members
        r"\b(mike johnson|john thune|hakeem jeffries|chuck schumer|katherine clark|steve scalise|elise stefanik|nancy pelosi|kevin mccarthy)\b",
        r"\b(ted cruz|josh hawley|lindsey graham|tom cotton|susan collins|lisa murkowski|joe manchin|kyrsten sinema|bernie sanders|elizabeth warren|cory booker|mark kelly|raphael warnock|jon ossoff|john fetterman)\b",
        r"\b(matt gaetz|marjorie taylor greene|lauren boebert|jim jordan|chip roy|adam schiff|dan crenshaw|byron donalds|wesley hunt)\b",
        # NYC mayoral race candidates (Mamdani et al.)
        r"\b(zohran mamdani|mamdani|eric adams|andrew cuomo|brad lander|scott stringer|jessica ramos|adrienne adams|whitney tilson|zellnor myrie|curtis sliwa|ritchie torres|letitia james)\b",
        # Other big-city mayors and gubernatorial candidates
        r"\b(karen bass|london breed|brandon johnson|john whitmire|mike duggan|lori lightfoot|muriel bowser|sylvester turner)\b",
        # SCOTUS justices
        r"\b(john roberts|clarence thomas|samuel alito|sonia sotomayor|elena kagan|neil gorsuch|brett kavanaugh|amy coney barrett|ketanji brown jackson)\b",
        # Prominent US political commentators / activists / candidates who don't always appear with party labels
        r"\b(charlie kirk|tucker carlson|jd vance|j\.d\. vance|vivek ramaswamy|rfk jr|robert f\.? kennedy|alexandria ocasio.cortez|aoc|mitt romney|ron desantis|kamala harris|tim walz|gavin newsom|josh shapiro|gretchen whitmer|wes moore|dan osborn|colin allred)\b",
        # Conservative & progressive media figures often in markets
        r"\b(steve bannon|laura loomer|nick fuentes|candace owens|ben shapiro|jordan peterson|scott jennings)\b",
        # Generic "next leader out" / replacement / no-confidence patterns
        r"\b(next leader out|no longer leader|no.confidence|step down|removed from office|next pm|next prime minister|next president|leave office|approval rating)\b",
    ]),
]

FIELDNAMES = [
    "id", "question", "slug", "event_slug", "yes_price", "no_price",
    "spread", "volume_usd", "liquidity_usd", "outcomes", "start_date",
    "end_date", "description", "category", "market_url",
    "moic_yes", "moic_no", "settlement_clarity",
]


# ---------------------------------------------------------------------------
# API-tag-based classification
# ---------------------------------------------------------------------------
# Polymarket's /events endpoint returns a `tags` array on each event with
# {id, label, slug, ...} entries. Tag labels and slugs are topic-bearing
# strings (e.g. "Soccer", "FIFA World Cup", "Politics", "OpenAI", "BTC", ...).
# We pattern-match on the concatenated label+slug string to map to our
# canonical categories. Crypto is checked first so that any crypto-adjacent
# tag triggers exclusion in filter_excluded().

TAG_CATEGORY_PATTERNS = [
    ("Crypto", [
        r"\bcrypto", r"bitcoin", r"\bbtc\b", r"ethereum", r"\beth\b",
        r"altcoin", r"stablecoin", r"\bdefi\b", r"\bnft\b", r"web3",
        r"solana", r"\bsol\b", r"dogecoin", r"\bdoge\b", r"airdrop",
        r"tokens?", r"coinbase", r"binance", r"uniswap", r"meme.coin",
        r"satoshi", r"celeb.coin", r"sam.bankman", r"sbf",
        r"hyperliquid", r"defi.app", r"story.protocol",
    ]),
    ("Esports", [
        r"\besports?\b", r"\blpl\b", r"\blcs\b", r"\blec\b", r"\blck\b",
        r"league.of.legends", r"lol.world", r"\bdota\b", r"the.international",
        r"valorant", r"\bvct\b", r"counter.strike", r"\bcs.go\b", r"\bcs2\b",
        r"overwatch.league", r"call.of.duty.league",
        r"\besl\b", r"\bheroic\b", r"\bnavi\b", r"\bfnatic\b",
        r"\bcloud9\b", r"\bg2\b", r"team.liquid", r"faze.clan",
        r"betboom", r"thundertalk", r"lgd.gaming",
    ]),
    ("Sports", [
        r"\bsports?\b", r"\bnfl\b", r"\bnba\b", r"\bmlb\b", r"\bnhl\b",
        r"\bwnba\b", r"\bmls\b", r"\bufc\b", r"\bmma\b", r"\bpga\b",
        r"\bipl\b", r"\bepl\b", r"soccer", r"\bfootball\b", r"basketball",
        r"baseball", r"\bhockey\b", r"\btennis\b", r"\bgolf\b", r"\bboxing\b",
        r"\bcricket\b", r"\brugby\b",
        r"\bf1\b", r"formula.1", r"grand.prix", r"olympics?",
        r"world.cup", r"\bfifa\b", r"champions.league", r"premier.league",
        r"la.liga", r"serie.a", r"bundesliga", r"ligue.1", r"europa.league",
        r"french.open", r"us.open", r"australian.open", r"wimbledon",
        r"super.bowl", r"world.series", r"stanley.cup", r"march.madness",
        r"\bmvp\b", r"heisman", r"cy.young", r"ballon", r"golden.boot",
        r"college.football", r"college.basketball",
        r"world.series.of.poker", r"redbull",
        r"\bnl.east\b", r"\bnl.west\b", r"\bnl.central\b",
        r"\bal.east\b", r"\bal.west\b", r"\bal.central\b",
        r"caitlin.clark", r"ohtani", r"angel.reese", r"swiatek",
        r"sainz", r"tom.aspinal", r"topuria", r"isak", r"tiger.woods",
        r"green.bay", r"dallas.cowboys", r"florida.panthers", r"san.jose.sharks",
        r"viktoria.plzen", r"slovan.bratislava", r"stoke.city", r"north.end",
        r"investec", r"super.rugby", r"bundesliga.2", r"lanka.premier",
        r"major.league.cricket", r"\bmnf\b", r"week.\d+",
        r"perfect.game", r"\bqb\b", r"draft", r"qualif",
    ]),
    ("Politics", [
        r"\bpolitics\b", r"\belection", r"\bvote\b", r"\bvoting\b",
        r"campaign", r"caucus", r"senate", r"sentate", r"congress",
        r"president", r"governor", r"\bmayor\b", r"prime.minister",
        r"chancellor", r"parliament", r"midterm", r"primary.election",
        r"runoff", r"ballot", r"impeach", r"resign", r"federal.government",
        r"house.races", r"democrat", r"republican", r"\bgop\b",
        r"bidenomics", r"nobel.peace.prize", r"foreign.policy",
        r"approval.rating", r"concession", r"caucus", r"barrasso",
        r"trump", r"biden", r"obama", r"newsom", r"pelosi", r"michelle.obama",
        r"mamdani", r"kash.patel", r"tulsi.gabbard", r"hegseth",
        r"vance", r"vivek", r"\baoc\b", r"klobuchar", r"thune",
        r"\bharris\b", r"walz", r"\btim.ryan\b", r"keith.gill",
        r"keir.starmer", r"sunak", r"farage", r"liz.truss", r"badenoch",
        r"xi.jinping", r"modi", r"trudeau", r"carney", r"poilievre",
        r"macron", r"meloni", r"milei", r"zelensky", r"sheinbaum",
        r"thailand.election",
    ]),
    ("Geopolitics", [
        r"geopolitic", r"international.affairs", r"foreign.affairs",
        r"\bwar\b", r"invasion", r"ceasefire", r"\bnato\b", r"military",
        r"missile", r"nuclear", r"drone.attack", r"hostage.crisis",
        r"\biraq\b", r"ukraine", r"russia", r"\bchina\b", r"\biran\b",
        r"north.korea", r"taiwan", r"venezuela", r"\bsyria\b",
        r"\byemen\b", r"\bisrael\b", r"palestine", r"\bgaza\b",
        r"hezbollah", r"hamas", r"\bcrimea\b", r"haniyeh",
        r"strait.of.hormuz", r"suez", r"maritime.transport",
        r"taliban", r"\bisis\b", r"al.qaeda", r"\basylum\b",
        r"\bkorea\b",
    ]),
    ("AI/Tech", [
        r"\bai\b", r"artificial.intelligence", r"\bagi\b", r"openai",
        r"anthropic", r"deepmind", r"chatgpt", r"\bgpt", r"gemini",
        r"\bclaude\b", r"\bllm\b", r"machine.learning", r"robotics",
        r"semiconductor", r"\bchip\b", r"autonomous.vehicles",
        r"self.driving", r"smart.home", r"cybertruck",
        r"\btech\b", r"silicon.valley", r"\bapple\b", r"\bgoogle\b",
        r"alphabet", r"microsoft", r"\bmeta\b", r"nvidia", r"tesla",
        r"amazon", r"oracle", r"salesforce", r"adobe", r"\bintel\b",
        r"\bamd\b", r"\bspacex\b", r"starlink", r"neuralink",
        r"\btwitter\b", r"\bmusk\b", r"waymo", r"\bcruise\b",
        r"\buber\b", r"\blyft\b", r"airbnb", r"stripe", r"palantir",
        r"snowflake", r"databricks",
        r"jensen.huang", r"sam.altman", r"zuckerberg", r"sergey.brin",
        r"vision.pro", r"iphone", r"\bipad\b", r"macbook",
        r"\bnasa\b", r"artemis", r"moon.mission", r"\bmars\b",
        r"\bjwst\b", r"james.webb", r"\bcod\b",
    ]),
    ("Entertainment", [
        r"entertainment", r"\bfilm\b", r"movies?", r"\boscar\b",
        r"academy.award", r"grammy", r"\bemmy\b", r"\btony\b",
        r"golden.globe", r"box.office", r"hollywood", r"sundance",
        r"netflix", r"disney", r"\bhbo\b", r"\bhulu\b", r"paramount",
        r"spotify", r"apple.music", r"youtube", r"tiktok",
        r"\balbum\b", r"\bsong\b", r"\bconcert\b", r"\btour\b",
        r"reality.tv", r"bachelor", r"bachelorette", r"survivor",
        r"big.brother", r"the.voice", r"american.idol", r"drag.race",
        r"love.island", r"season.\d+", r"season.finale",
        r"celebrity", r"kardashian", r"jenner", r"taylor.swift",
        r"travis.kelce", r"\bdrake\b", r"beyonce", r"rihanna",
        r"timothee.chalamet", r"chalamet", r"asap.rocky", r"lana.del.rey",
        r"ariana.grande", r"billie.eilish", r"olivia.rodrigo",
        r"sabrina.carpenter", r"chappell.roan",
        r"video.game", r"\bgta\b", r"grand.theft.auto",
        r"minecraft", r"fortnite", r"roblox",
        r"podcast", r"joe.rogan", r"theo.von", r"lex.fridman",
        r"mrbeast", r"mr.beast", r"\bksi\b", r"andrew.tate",
        r"\bnelk\b", r"adam.22", r"hasan.piker", r"\bjames.bond\b",
        r"\bbond\b",
    ]),
    ("Religion", [
        r"\bjesus\b", r"\bchrist\b", r"messiah", r"biblical",
        r"\bpope\b", r"vatican", r"papal", r"conclave",
        r"\bislam\b", r"\bmuslim\b", r"christianity", r"\bchristian\b",
        r"judaism", r"\bjewish\b", r"\bhindu\b", r"\bbuddhist\b",
        r"catholic", r"protestant", r"evangelical", r"religion",
    ]),
    ("Weather", [
        r"weather", r"\bclimate\b", r"hurricane", r"tornado", r"typhoon",
        r"cyclone", r"tropical.storm", r"wildfire", r"\bflood",
        r"drought", r"earthquake", r"tsunami", r"volcano", r"volcanic",
        r"\bvei\b", r"asteroid", r"meteor", r"el.ni", r"la.ni",
        r"hottest", r"coldest", r"warmest", r"heat.wave", r"\bcop\d*\b",
    ]),
    ("Health", [
        r"healthcare", r"pharma", r"\bhhs\b", r"\bnih\b", r"\bcdc\b",
        r"\bwho\b", r"\bfda\b", r"vaccine", r"pandemic", r"epidemic",
        r"\bcovid\b", r"\bsars\b", r"\bmers\b", r"coronavirus",
        r"flu.season", r"influenza", r"\bh5n1\b", r"bird.flu",
        r"mpox", r"monkeypox", r"\bebola\b", r"marburg", r"\bzika\b",
        r"dengue", r"cholera", r"tuberculosis", r"measles", r"\bpolio\b",
        r"ozempic", r"wegovy", r"semaglutide", r"\bglp\b",
        r"alzheimer", r"crispr", r"\bmrna\b", r"biotech",
        r"gene.therapy", r"life.expectancy",
    ]),
    ("Legal/Crime", [
        r"legal.cases", r"\bcourt\b", r"\bjudge\b", r"\bruling\b",
        r"lawsuit", r"indictment", r"convicted", r"sentenced",
        r"verdict", r"supreme.court", r"\bscotus\b", r"\btrial\b",
        r"prosecution", r"\bprison\b", r"\bjail\b", r"shooting",
        r"murder", r"\bcrime\b", r"arrest", r"\bfbi\b",
        r"epstein", r"diddy", r"\bcosby\b", r"sam.bankman",
        r"controversies",
    ]),
    ("Economics", [
        r"\beconomy\b", r"economic", r"\bgdp\b", r"\bcpi\b", r"\bppi\b",
        r"inflation", r"recession", r"unemployment", r"interest.rate",
        r"federal.reserve", r"\bfed\b", r"central.bank",
        r"tariff", r"trade.war", r"\bsanctions\b", r"treasury",
        r"\bs.p\b", r"dow.jones", r"nasdaq", r"stock.market",
        r"\bipo\b", r"\betf\b", r"\bfdic\b", r"macro",
        r"oil.price", r"commodit", r"\bsilver\b", r"\bgold\b",
        r"copper", r"\bwti\b", r"\bbrent\b", r"natural.gas",
        r"goldman", r"jpmorgan", r"\bubs\b", r"credit.suisse",
        r"\bcitibank\b", r"morgan.stanley", r"deutsche.bank",
        r"bankruptcy", r"bank.fail", r"bank.run",
        r"richest", r"billionaire", r"net.worth",
        r"buffett", r"jeff.bezos", r"arnault", r"audemars.piguet",
    ]),
]


def classify_from_tags(event_tags):
    """
    Given an event's `tags` list (from the Gamma API), try to classify it
    using the tag labels and slugs. Returns a category string or None when
    no tag pattern matches (fall back to regex classifier).
    """
    if not event_tags:
        return None
    text = " ".join(
        ((t.get("label", "") or "") + " " + (t.get("slug", "") or ""))
        for t in event_tags if isinstance(t, dict)
    ).lower()
    if not text.strip():
        return None
    for cat, patterns in TAG_CATEGORY_PATTERNS:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return cat
    return None


def classify_market(question, description="", slug="", event_slug="", event_title=""):
    """
    Classify a market into a category by regex-matching question + description +
    slug + event_slug + event_title. Slugs and event titles are essential signal:
    e.g. event_slug="2026-fifa-world-cup-winner-595" tells us it's Sports even when
    the individual market question is just "Will Brazil win?".
    Slugs are dash-separated; \\b word boundaries treat dashes as separators, so
    regex matches transparently.
    """
    parts = [question or "", description or "", slug or "", event_slug or "", event_title or ""]
    text = " ".join(parts).lower()
    for cat, patterns in CATEGORY_RULES:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return cat
    return "Other"


def fetch_all_events():
    all_events = []
    offset = 0
    print("Fetching active events from Polymarket Gamma API...")
    print("-" * 50)

    while True:
        params = {**FILTERS, "offset": offset}
        try:
            response = requests.get(EVENTS_ENDPOINT, params=params, timeout=15)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"\n[ERROR] API request failed: {e}")
            sys.exit(1)

        batch = response.json()
        if not batch:
            break

        all_events.extend(batch)
        total_markets = sum(len(e.get("markets", [])) for e in all_events)
        print(f"  Fetched {len(all_events)} events ({total_markets} markets) so far... (offset={offset})")

        if len(batch) < PAGE_SIZE:
            break
        if MAX_EVENTS and len(all_events) >= MAX_EVENTS:
            all_events = all_events[:MAX_EVENTS]
            break

        offset += PAGE_SIZE
        time.sleep(0.3)

    total_markets = sum(len(e.get("markets", [])) for e in all_events)
    print(f"\nTotal events fetched: {len(all_events)} containing {total_markets} markets")
    return all_events


def extract_markets_from_events(events):
    rows = []
    skipped_closed = 0

    for event in events:
        event_slug = event.get("slug", "")
        event_title = event.get("title", "")
        event_tags = event.get("tags", []) or []
        # Try API-provided tags first; fall back to regex if no usable tag matched.
        api_category = classify_from_tags(event_tags)
        nested_markets = event.get("markets", []) or [event]

        for m in nested_markets:
            if str(m.get("closed", "false")).lower() == "true":
                skipped_closed += 1
                continue

            outcome_prices = m.get("outcomePrices", "[]")
            try:
                prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
            except (json.JSONDecodeError, TypeError):
                prices = []

            yes_price = float(prices[0]) if len(prices) > 0 else None
            no_price = float(prices[1]) if len(prices) > 1 else None

            outcomes_raw = m.get("outcomes", "[]")
            if isinstance(outcomes_raw, str):
                try:
                    outcomes = json.loads(outcomes_raw)
                except (json.JSONDecodeError, TypeError):
                    outcomes = []
            else:
                outcomes = outcomes_raw if outcomes_raw else []

            market_slug = m.get("slug", "")
            if event_slug and market_slug and event_slug != market_slug:
                url = f"https://polymarket.com/event/{event_slug}/{market_slug}"
            elif event_slug:
                url = f"https://polymarket.com/event/{event_slug}"
            else:
                url = f"https://polymarket.com/event/{market_slug}"

            question = m.get("question", event_title)
            description = (m.get("description") or event.get("description") or "")[:200]

            rows.append({
                "id": m.get("id", event.get("id")),
                "question": question,
                "slug": market_slug,
                "event_slug": event_slug,
                "yes_price": yes_price,
                "no_price": no_price,
                "spread": round(abs((yes_price or 0) - (1 - (no_price or 1))), 4) if yes_price and no_price else None,
                "volume_usd": float(m.get("volume", 0) or 0),
                "liquidity_usd": float(m.get("liquidity", 0) or 0),
                "outcomes": ", ".join(outcomes) if outcomes else "",
                "start_date": m.get("startDate", event.get("startDate")),
                "end_date": m.get("endDate", event.get("endDate")),
                "description": description,
                "category": api_category or classify_market(question, description, market_slug, event_slug, event_title),
                "market_url": url,
            })

    # Dedup by id
    seen = set()
    unique = []
    for r in rows:
        rid = r.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        unique.append(r)
    if len(rows) - len(unique) > 0:
        print(f"  Removed {len(rows) - len(unique)} duplicate markets")

    print(f"  Skipped {skipped_closed} closed markets")

    unique.sort(key=lambda r: r.get("volume_usd") or 0, reverse=True)
    return unique


def filter_excluded(rows):
    # Drop markets that resolve today or earlier — user policy: no same-day expiry.
    today = datetime.now().date()
    def keeps_date(r):
        ed = r.get("end_date")
        if not ed:
            return True
        try:
            return datetime.fromisoformat(str(ed).replace("Z", "+00:00")).date() > today
        except (ValueError, TypeError):
            return True
    before = len(rows)
    rows = [r for r in rows if keeps_date(r)]
    print(f"  Filtered out {before - len(rows)} same-day or expired markets (excluded by policy)")

    before = len(rows)
    rows = [r for r in rows if (r.get("liquidity_usd") or 0) >= MIN_LIQUIDITY]
    print(f"  Filtered out {before - len(rows)} markets below ${MIN_LIQUIDITY:,} liquidity")

    before = len(rows)
    rows = [r for r in rows if (r.get("volume_usd") or 0) >= MIN_VOLUME]
    print(f"  Filtered out {before - len(rows)} markets below ${MIN_VOLUME:,} volume")

    if EXCLUDED_KEYWORDS:
        before = len(rows)
        def keep(r):
            text = ((r.get("question") or "") + " " + (r.get("category") or "") + " " + (r.get("description") or "")).lower()
            return not any(kw in text for kw in EXCLUDED_KEYWORDS)
        rows = [r for r in rows if keep(r)]
        print(f"  Filtered out {before - len(rows)} markets (excluded keywords)")

    print(f"  Remaining: {len(rows)} markets")
    return rows


def add_trading_metrics(rows):
    for r in rows:
        yp = r.get("yes_price")
        np_ = r.get("no_price")
        r["moic_yes"] = round(1.0 / yp, 2) if yp and yp > 0.01 else None
        r["moic_no"] = round(1.0 / np_, 2) if np_ and np_ > 0.01 else None

        score = 3
        if r.get("end_date"):
            score += 1
        if r.get("outcomes") and r["outcomes"].lower() in ["yes, no"]:
            score += 1
        if not r.get("description") or len(str(r.get("description", ""))) < 20:
            score -= 1
        r["settlement_clarity"] = min(max(score, 1), 5)
    return rows


def export_to_csv(rows):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"polymarket_active_{timestamp}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nExported {len(rows)} markets to: {filename}")
    return filename


def print_summary(rows):
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_vol = sum((r.get("volume_usd") or 0) for r in rows)
    avg_liq = sum((r.get("liquidity_usd") or 0) for r in rows) / len(rows) if rows else 0
    print(f"Total active markets:    {len(rows)}")
    print(f"Total volume (all mkts): ${total_vol:,.0f}")
    print(f"Avg liquidity:           ${avg_liq:,.0f}")

    print(f"\n--- BY CATEGORY ---")
    cat_counts = Counter(r.get("category", "Other") for r in rows)
    for cat, count in cat_counts.most_common():
        print(f"  {cat:20s} {count:4d} markets")

    print(f"\n--- TOP 30 BY VOLUME ---")
    print(f"{'Question':<70} {'YES':>7} {'Volume':>14} {'MOIC':>7} {'SC':>4}")
    for r in rows[:30]:
        q = (r.get("question") or "")[:70]
        yp = r.get("yes_price") or 0
        vol = r.get("volume_usd") or 0
        moic = r.get("moic_yes") or 0
        sc = r.get("settlement_clarity") or 0
        print(f"{q:<70} {yp:>7.3f} {vol:>14,.0f} {moic:>7.2f} {sc:>4}")


if __name__ == "__main__":
    events = fetch_all_events()
    if not events:
        print("No active events found. Exiting.")
        sys.exit(0)

    print("\n--- TOP 10 EVENTS BY MARKET COUNT ---")
    events_sorted = sorted(events, key=lambda e: len(e.get("markets", [])), reverse=True)
    for e in events_sorted[:10]:
        mkts = e.get("markets", [])
        print(f"  {len(mkts):4d} markets | closed={str(e.get('closed','')):5s} | {(e.get('title') or '???')[:60]}")

    rows = extract_markets_from_events(events)
    print(f"\nExtracted {len(rows)} unique markets from {len(events)} events")

    print("\n--- DIAGNOSTIC: Searching for known big markets ---")
    for keyword in ["2028", "netanyahu", "iran strike", "chelsea clinton", "oprah"]:
        matches = [r for r in rows if keyword in (r.get("question") or "").lower()]
        if matches:
            top_vol = max((r.get("volume_usd") or 0) for r in matches)
            print(f"  FOUND '{keyword}': {len(matches)} markets (top vol: ${top_vol:,.0f})")
        else:
            print(f"  MISSING '{keyword}'")

    rows = filter_excluded(rows)
    rows = add_trading_metrics(rows)
    filename = export_to_csv(rows)
    print_summary(rows)

    print(f"\nDone! Open {filename} in Excel or Google Sheets for full data.")
