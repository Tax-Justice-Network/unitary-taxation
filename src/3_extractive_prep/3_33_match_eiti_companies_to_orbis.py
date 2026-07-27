"""
Attach an HQ (global-ultimate-owner) country to every EITI company, by matching the
EITI company name against the *full* Orbis extractive-entity universe.

The universe (`orbis_entity_universe.csv`, built by 1_7a) has ~600k entities — including
the local operating subsidiaries — each carrying its GUO bvd-id / name / type / country.
An EITI payment in country C is made by an entity operating in C, which is almost always
*incorporated in C*, so we match the EITI name against the Orbis entities with
`entity_country == C` first, and only fall back to a global match.  For a matched entity:
  - HQ country  = the matched entity's `guo_country`
  - is it in the CbCR universe?  = the matched entity's `in_cbcr_universe` flag (a multi-entity
    extractive group above the €750M turnover threshold) — used in 1_8 to decide whether the
    *domestic* portion of a payment lands on a CbCR cell or is kept out of scope.
A hand-curated override list (major operators / NOCs) is still applied first as a fast path.

Input:  data/intermediate/extractive/eiti_company_payments_long.csv     (1_6)
        data/intermediate/extractive/orbis_entity_universe.csv          (1_7a)
Output: data/intermediate/extractive/eiti_company_hq_map.csv
        one row per (source iso3, EITI company): matched Orbis entity + bvd_id, GUO name/type,
        hq_iso3, in_cbcr_universe, match method & score, payment value & row count.
"""
import csv
import re
import sys
import unicodedata
from collections import defaultdict

from rapidfuzz import process, fuzz
import pycountry

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

EITI_PAY = EXT_INT / "eiti_company_payments_long.csv"
UNIVERSE = EXT_INT / "orbis_entity_universe.csv"
OUT = EXT_INT / "eiti_company_hq_map.csv"

FUZZY_THRESHOLD = 90

# Hand-curated overrides for major operators / NOCs. Keyed on a distinctive normalised
# substring (matched as a contiguous word-run in the EITI name). value = (canonical name, HQ iso2,
# is_cbcr_filer) — is_cbcr_filer defaults True; set False for pure-domestic SDFI vehicles / NOCs that
# do NOT file CbCR (so their domestic payments don't land on a CbCR diagonal cell). For entries with
# no explicit flag the Orbis universe's in_cbcr_universe is consulted if the canonical name is found.
_OVR = [
    ("nigerian national petroleum", ("NNPC", "NG", False)), ("nnpc", ("NNPC", "NG", False)),
    ("petronas", ("Petronas", "MY")), ("petroliam nasional", ("Petronas", "MY")),
    ("sonatrach", ("Sonatrach", "DZ", False)), ("pertamina", ("Pertamina", "ID")),
    ("petroleos mexicanos", ("Pemex", "MX")), ("pemex", ("Pemex", "MX")),
    ("petrobras", ("Petrobras", "BR")), ("petroleo brasileiro", ("Petrobras", "BR")),
    ("kuwait petroleum", ("Kuwait Petroleum Corp", "KW", False)), ("kuwait oil company", ("Kuwait Oil Co", "KW", False)),
    ("abu dhabi national oil", ("ADNOC", "AE")), ("adnoc", ("ADNOC", "AE")),
    ("qatar petroleum", ("QatarEnergy", "QA", False)), ("qatarenergy", ("QatarEnergy", "QA", False)),
    ("national iranian oil", ("NIOC", "IR", False)),
    ("gazprom", ("Gazprom", "RU")), ("rosneft", ("Rosneft", "RU")), ("lukoil", ("Lukoil", "RU")),
    ("equinor", ("Equinor", "NO")), ("statoil", ("Equinor", "NO")), ("petoro", ("Petoro", "NO", False)),
    ("energie beheer nederland", ("Energie Beheer Nederland", "NL", False)), ("nederlandse aardolie", ("NAM (Shell/ExxonMobil)", "NL")),
    ("ecopetrol", ("Ecopetrol", "CO")), ("ypf", ("YPF", "AR")), ("pdvsa", ("PDVSA", "VE", False)),
    ("petronor", ("Petronor", "AO", False)), ("sonangol", ("Sonangol", "AO", False)),
    ("ghana national petroleum", ("GNPC", "GH", False)), ("gnpc", ("GNPC", "GH", False)),
    ("societe nationale des petroles du congo", ("SNPC", "CG", False)), ("societe nationale des hydrocarbures", ("SNH", "CM", False)),
    ("gabon oil company", ("Gabon Oil Co", "GA", False)),
    ("petrosen", ("Petrosen", "SN", False)), ("petroci", ("Petroci", "CI", False)),
    ("glencore", ("Glencore", "CH")), ("trafigura", ("Trafigura", "CH")), ("vitol", ("Vitol", "CH")),
    ("barrick", ("Barrick Gold", "CA")), ("kinross", ("Kinross Gold", "CA")), ("iamgold", ("IAMGOLD", "CA")),
    ("b2gold", ("B2Gold", "CA")), ("endeavour mining", ("Endeavour Mining", "GB")), ("perseus mining", ("Perseus Mining", "AU")),
    ("anglogold ashanti", ("AngloGold Ashanti", "ZA")), ("gold fields", ("Gold Fields", "ZA")), ("harmony gold", ("Harmony Gold", "ZA")),
    ("newmont", ("Newmont", "US")), ("freeport", ("Freeport-McMoRan", "US")),
    ("rio tinto", ("Rio Tinto", "GB")), ("bhp", ("BHP", "AU")), ("vedanta", ("Vedanta", "GB")), ("anglo american", ("Anglo American", "GB")),
    ("china molybdenum", ("CMOC / China Molybdenum", "CN")), ("cmoc", ("CMOC / China Molybdenum", "CN")),
    ("zijin mining", ("Zijin Mining", "CN")), ("sinohydro", ("Sinohydro / PowerChina", "CN")),
    ("china national petroleum", ("CNPC", "CN")), ("cnooc", ("CNOOC", "CN")), ("sinopec", ("Sinopec", "CN")),
    ("shell", ("Shell", "GB")), ("totalenergies", ("TotalEnergies", "FR")), ("total e&p", ("TotalEnergies", "FR")), ("elf", ("TotalEnergies", "FR")),
    ("exxonmobil", ("ExxonMobil", "US")), ("exxon mobil", ("ExxonMobil", "US")), ("esso", ("ExxonMobil", "US")),
    ("chevron", ("Chevron", "US")), ("conocophillips", ("ConocoPhillips", "US")),
    ("eni ", ("Eni", "IT")), ("agip", ("Eni", "IT")), ("repsol", ("Repsol", "ES")), ("bp ", ("BP", "GB")),
    ("kosmos energy", ("Kosmos Energy", "US")), ("tullow oil", ("Tullow Oil", "GB")), ("woodside", ("Woodside Energy", "AU")),
    ("wintershall", ("Wintershall Dea", "DE")), ("wintershall dea", ("Wintershall Dea", "DE")),
    ("spirit energy", ("Spirit Energy", "GB")), ("neptune energy", ("Neptune Energy", "GB")),
    ("var energi", ("Vår Energi", "NO")), ("vaar energi", ("Vår Energi", "NO")), ("aker bp", ("Aker BP", "NO")),
    ("omv", ("OMV", "AT")), ("pgnig", ("PGNiG", "PL")), ("taqa", ("TAQA", "AE")), ("lundin", ("Lundin Energy", "SE")),
    ("dno asa", ("DNO", "NO")), ("vaalco", ("Vaalco Energy", "US")), ("genel energy", ("Genel Energy", "GB")),
    ("gulf keystone", ("Gulf Keystone Petroleum", "GB")), ("siccar point", ("Siccar Point Energy", "GB")),
    ("harbour energy", ("Harbour Energy", "GB")), ("ithaca energy", ("Ithaca Energy", "GB")), ("serica energy", ("Serica Energy", "GB")),
    ("cnr international", ("Canadian Natural Resources", "CA")), ("canadian natural", ("Canadian Natural Resources", "CA")),
    ("petrofac", ("Petrofac", "GB")), ("schlumberger", ("Schlumberger", "US")), ("halliburton", ("Halliburton", "US")),
    ("baker hughes", ("Baker Hughes", "US")), ("technip", ("TechnipFMC", "GB")), ("saipem", ("Saipem", "IT")),
    ("subsea 7", ("Subsea 7", "GB")), ("aker solutions", ("Aker Solutions", "NO")), ("seadrill", ("Seadrill", "GB")),
    ("ukrnafta", ("Ukrnafta", "UA", False)), ("ukrgazvydobuvannya", ("Ukrgazvydobuvannya", "UA", False)), ("ukrtransgaz", ("Ukrtransgaz", "UA", False)),
    ("ukrtransnafta", ("Ukrtransnafta", "UA", False)), ("naftogaz", ("Naftogaz", "UA", False)),
    ("snim", ("SNIM", "MR", False)), ("societe nationale industrielle et miniere", ("SNIM", "MR", False)),
    ("yinka folawiyo", ("Yinka Folawiyo Petroleum", "NG", False)), ("seplat", ("Seplat Energy", "NG", False)), ("oando", ("Oando", "NG", False)),
    ("shell petroleum development company", ("SPDC (Shell)", "GB")), ("spdc", ("SPDC (Shell)", "GB")),
    ("addax", ("Addax Petroleum (Sinopec)", "CN")), ("first e&p", ("First E&P", "NG", False)),
    ("basra oil", ("Basra Oil Company", "IQ", False)), ("missan oil", ("Missan Oil Company", "IQ", False)), ("midland oil", ("Midland Oil Company", "IQ", False)),
    ("south oil company", ("South Oil Company", "IQ", False)), ("north oil company", ("North Oil Company", "IQ", False)), ("somo", ("SOMO (Iraq)", "IQ", False)),
    ("lake asphalt", ("Lake Asphalt of T&T", "TT", False)), ("trinidad petroleum holdings", ("Trinidad Petroleum Holdings", "TT", False)), ("heritage petroleum", ("Heritage Petroleum", "TT", False)), ("national gas company of trinidad", ("NGC Trinidad", "TT", False)),
    ("petroleum company of trinidad", ("Petrotrin", "TT", False)), ("petrotrin", ("Petrotrin", "TT", False)), ("touchstone", ("Touchstone Exploration", "CA")),
    ("perupetro", ("Perupetro", "PE", False)), ("petroperu", ("Petroperu", "PE", False)),
    ("petroamazonas", ("Petroamazonas", "EC", False)), ("petroecuador", ("Petroecuador", "EC", False)),
    ("oil and natural gas corporation", ("ONGC", "IN")), ("ongc videsh", ("ONGC Videsh", "IN")), ("ongc", ("ONGC", "IN")),
    ("oil india", ("Oil India", "IN")), ("indian oil", ("Indian Oil Corp", "IN")), ("reliance industries", ("Reliance Industries", "IN")),
    ("hindustan petroleum", ("Hindustan Petroleum", "IN")), ("hpcl", ("Hindustan Petroleum", "IN")), ("bharat petroleum", ("Bharat Petroleum", "IN")),
    ("essar oil", ("Essar Oil", "IN")), ("cairn", ("Vedanta / Cairn", "GB")),
    ("tupras", ("Tupras", "TR")), ("turkish petroleum", ("TPAO (Turkish Petroleum)", "TR", False)), ("tpao", ("TPAO (Turkish Petroleum)", "TR", False)),
    ("sinochem", ("Sinochem", "CN")), ("zhenhua oil", ("China Zhenhua Oil", "CN")), ("petrochina", ("PetroChina", "CN")),
    ("china offshore oil", ("CNOOC", "CN")), ("unipec", ("Unipec (Sinopec)", "CN")), ("geo-jade", ("Geo-Jade Petroleum", "CN")),
    ("united energy group", ("United Energy Group", "CN")), ("litasco", ("Litasco (Lukoil)", "RU")),
    ("nfc africa", ("CNMC", "CN")), ("non-ferrous company africa", ("CNMC", "CN")), ("cnmc", ("CNMC", "CN")), ("china nonferrous", ("CNMC", "CN")),
    ("luanshya copper", ("Luanshya Copper (CNMC)", "CN")), ("chambishi", ("Chambishi (CNMC)", "CN")),
    ("first quantum", ("First Quantum Minerals", "CA")), ("kansanshi", ("First Quantum Minerals", "CA")), ("kalumbila", ("First Quantum Minerals", "CA")),
    ("konkola copper", ("Konkola Copper Mines", "GB")), ("mopani", ("Mopani Copper Mines", "ZM", False)), ("zccm", ("ZCCM-IH", "ZM", False)),
    ("kcm", ("Konkola Copper Mines", "GB")), ("lumwana", ("Lumwana (Barrick)", "CA")),
    ("pluspetrol", ("Pluspetrol", "AR")), ("hochschild", ("Hochschild Mining", "PE")), ("buenaventura", ("Buenaventura", "PE")), ("southern copper", ("Southern Copper (Grupo México)", "MX")),
    ("antamina", ("Antamina (BHP/Glencore/etc.)", "AU")), ("yanacocha", ("Yanacocha (Newmont)", "US")), ("las bambas", ("Las Bambas (MMG)", "AU")),
    ("mmg ", ("MMG", "AU")), ("volcan compania minera", ("Volcan / Glencore", "CH")),
    ("nido petroleum", ("Nido Petroleum", "AU")), ("philex", ("Philex Mining", "PH")),
    ("semirara", ("Semirara Mining (Consunji)", "PH")), ("benguet corporation", ("Benguet Corp", "PH")),
    ("kibali", ("Kibali (Barrick/AngloGold)", "CA")), ("banro", ("Banro Corp", "CA")), ("ivanhoe", ("Ivanhoe Mines", "CA")),
    ("kamoa", ("Ivanhoe Mines", "CA")), ("tenke fungurume", ("CMOC (Tenke Fungurume)", "CN")), ("metalkol", ("ERG (Metalkol)", "LU")),
    ("eurasian resources", ("ERG", "LU")), ("erg ", ("ERG", "LU")), ("boss mining", ("ERG", "LU")), ("comide", ("ERG", "LU")),
    ("societe miniere de bakwanga", ("MIBA", "CD", False)), ("miba", ("MIBA", "CD", False)), ("gecamines", ("Gécamines", "CD", False)), ("sodimico", ("Sodimico", "CD", False)),
    ("randgold", ("Barrick (ex-Randgold)", "CA")), ("loulo", ("Barrick (Loulo-Gounkoto)", "CA")), ("gounkoto", ("Barrick (Loulo-Gounkoto)", "CA")),
    ("fekola", ("B2Gold (Fekola)", "CA")), ("syama", ("Resolute Mining (Syama)", "GB")), ("resolute mining", ("Resolute Mining", "GB")),
    ("morila", ("Morila (Firefinch)", "AU")), ("sadiola", ("Sadiola (Allied Gold)", "AU")),
    ("essakane", ("IAMGOLD (Essakane)", "CA")), ("bissa gold", ("Nordgold (Bissa)", "RU")), ("nordgold", ("Nordgold", "RU")),
    ("semafo", ("Endeavour Mining (ex-Semafo)", "GB")), ("teranga gold", ("Endeavour Mining (ex-Teranga)", "GB")),
    ("roxgold", ("Fortuna Silver (Roxgold)", "CA")), ("hounde", ("Endeavour Mining (Houndé)", "GB")), ("netiana", ("Netiana Mining", "BF", False)),
    ("sissingue", ("Perseus Mining (Sissingué)", "AU")), ("yaoure", ("Perseus Mining (Yaouré)", "AU")),
    ("centamin", ("Centamin", "GB")), ("allied gold", ("Allied Gold", "AU")),
    ("avocet mining", ("Avocet Mining", "GB")), ("hummingbird resources", ("Hummingbird Resources", "GB")), ("yanfolila", ("Hummingbird Resources (Yanfolila)", "GB")),
    ("chirano", ("Kinross Gold (Chirano)", "CA")), ("tasiast", ("Kinross Gold (Tasiast)", "CA")),
    ("goldfields ghana", ("Gold Fields", "ZA")), ("damang", ("Gold Fields (Damang)", "ZA")), ("tarkwa", ("Gold Fields (Tarkwa)", "ZA")),
    ("obuasi", ("AngloGold Ashanti (Obuasi)", "ZA")), ("iduapriem", ("AngloGold Ashanti (Iduapriem)", "ZA")),
    ("newmont ghana", ("Newmont", "US")), ("ahafo", ("Newmont (Ahafo)", "US")), ("akyem", ("Newmont (Akyem)", "US")),
    ("asanko", ("Galiano Gold (Asanko)", "CA")), ("galiano", ("Galiano Gold", "CA")), ("golden star", ("Golden Star Resources", "US")),
    ("edikan", ("Perseus Mining (Edikan)", "AU")),
    ("ghana manganese", ("Ghana Manganese (Consmin)", "GB")), ("consolidated minerals", ("Consmin", "GB")),
    ("ghana bauxite", ("Ghana Bauxite", "GH", False)), ("giadec", ("GIADEC", "GH", False)),
    ("kabang", ("Kabanga Nickel", "GB")), ("petra diamonds", ("Petra Diamonds", "GB")), ("williamson diamonds", ("Petra Diamonds (Williamson)", "GB")),
    ("acacia mining", ("Barrick (ex-Acacia)", "CA")), ("north mara", ("Barrick (North Mara)", "CA")), ("bulyanhulu", ("Barrick (Bulyanhulu)", "CA")), ("buzwagi", ("Barrick (Buzwagi)", "CA")),
    ("geita gold", ("AngloGold Ashanti (Geita)", "ZA")), ("shanta gold", ("Shanta Gold", "GB")),
    ("songas", ("Songas (Globeleq)", "GB")), ("pan african energy tanzania", ("Maurel & Prom (M&P)", "FR")), ("maurel", ("Maurel & Prom", "FR")),
    ("orca exploration", ("Orca Energy", "CA")), ("wentworth resources", ("Wentworth Resources", "GB")),
    ("solaris resources", ("Solaris Resources", "CA")), ("enami", ("ENAMI", "CL", False)), ("codelco", ("Codelco", "CL")),
    ("lundin gold", ("Lundin Gold", "CA")), ("fruta del norte", ("Lundin Gold (Fruta del Norte)", "CA")), ("mirador", ("Tongling/CRCC (Mirador)", "CN")),
    ("andes petroleum", ("CNPC/Sinopec (Andes Petroleum)", "CN")), ("petrooriental", ("CNPC/Sinopec (PetroOriental)", "CN")),
    ("simandou", ("Rio Tinto / Winning Consortium (Simandou)", "GB")), ("compagnie des bauxites de guinee", ("CBG (Alcoa/Rio Tinto/Dadco)", "US")), ("cbg ", ("CBG", "US")),
    ("guinea alumina", ("Emirates Global Aluminium (GAC)", "AE")), ("ega ", ("Emirates Global Aluminium", "AE")), ("rusal", ("Rusal", "RU")), ("friguia", ("Rusal (Friguia)", "RU")),
    ("societe miniere de boke", ("SMB-Winning (bauxite)", "SG")), ("smb ", ("SMB-Winning", "SG")), ("winning consortium", ("SMB-Winning", "SG")),
    ("nimba", ("ArcelorMittal / SMFG (Nimba)", "LU")), ("arcelormittal", ("ArcelorMittal", "LU")),
    ("societe aurifere de guinee", ("SAG (AngloGold)", "ZA")), ("siguiri", ("AngloGold Ashanti (Siguiri)", "ZA")),
    ("petromar", ("Sonangol Pesquisa & Produção", "AO", False)),

    # ── 2026-05-15: HQ override additions covering ~$300B of EITI payments that
    # were dropped as "unmatched" by the Orbis fuzzy matcher. Derived from
    # eiti_company_hq_map.csv unmatched audit. Grouped by country for clarity.
    # is_cbcr_filer=False is set for state-owned vehicles / national oil
    # companies that do not file CbCR (so their domestic-only payments don't
    # populate the CbCR diagonal cell).
    #
    # ── DRC (COD) — Glencore + Perenco + Chinese miners + state ──
    ("mutanda", ("Mutanda Mining (Glencore)", "CH")),
    ("kamoto copper", ("KCC (Glencore)", "CH")),
    ("muanda international oil", ("MIOC (Perenco)", "FR")),
    ("perenco", ("Perenco", "FR")),
    ("perencorep", ("Perenco-Rep", "FR")),
    ("teikoku", ("INPEX (Teikoku)", "JP")),
    ("ruashi", ("Ruashi Mining (Jinchuan)", "CN")),
    ("congo dongfang", ("Huayou Cobalt (CDM)", "CN")),
    ("dongfang international mining", ("Huayou Cobalt (CDM)", "CN")),
    ("amck mining", ("AMCK / Kinsevere (MMG)", "AU")),
    ("kinsevere", ("MMG Kinsevere", "AU")),
    ("musonoie", ("Musonoie Global (Chengtun)", "CN")),
    ("kalumbwe", ("Kalumbwe Myunga (Chengtun)", "CN")),
    ("kipoi", ("Société d'Exploitation de Kipoi (Tiger Resources)", "AU")),
    ("frontier sa", ("Frontier (ERG)", "LU")),
    ("frontier sprl", ("Frontier (ERG)", "LU")),
    ("tfm", ("CMOC Tenke Fungurume", "CN")),
    ("lirex", ("Lirex SARL (DRC fuel distributor)", "CD", False)),

    # ── Chad (TCD) — SHT (state), CNPC, Glencore (ex-Caracal), TOTCO/ExxonMobil JV ──
    ("societe des hydrocarbures du tchad", ("SHT", "TD", False)),
    ("sht ", ("SHT", "TD", False)),
    ("societe de raffinage de n", ("SRN (CNPC+TD)", "TD", False)),
    ("griffiths energy", ("Caracal Energy (Glencore)", "CH")),
    ("caracal energy", ("Caracal Energy (Glencore)", "CH")),
    ("cnpci", ("CNPC International", "CN")),
    ("tchad oil transportation", ("TOTCO (Chad pipeline)", "TD", False)),
    ("totco", ("TOTCO", "TD", False)),
    ("eepci", ("ExxonMobil Chad (EEPCI)", "US")),
    ("esso exploration and production chad", ("ExxonMobil Chad", "US")),
    ("united hydrocarbon chad", ("Delonex / United Hydrocarbon", "GB")),
    ("sogea satom", ("Vinci Construction (Sogea-Satom)", "FR")),

    # ── Niger (NER) — Orano uranium + CNPC oil + state ──
    ("cnpc niger", ("CNPC Niger", "CN")),
    ("somair", ("Orano (SOMAÏR)", "FR")),
    ("societe des mines de l air", ("Orano (SOMAÏR)", "FR")),
    ("cominak", ("Orano (COMINAK)", "FR")),
    ("compagnie miniere d akouta", ("Orano (COMINAK)", "FR")),
    ("somina", ("SOMINA (CNNC)", "CN")),
    ("soraz", ("SORAZ Refinery (CNPC)", "CN")),
    ("societe des mines d azelik", ("SOMINA (CNNC)", "CN")),

    # ── Mozambique (MOZ) — Anadarko/Total + Vale + Sasol + Cove/PTT + Gemfields ──
    ("anadarko mocambique", ("TotalEnergies (Mozambique LNG, ex-Anadarko)", "FR")),
    ("anadarko", ("Occidental Petroleum (Anadarko)", "US")),
    ("vale mocambique", ("Vale (Moatize)", "BR")),
    ("vale moçambique", ("Vale (Moatize)", "BR")),
    ("cove energy", ("PTTEP (Cove Energy)", "TH")),
    ("rompco", ("Sasol Gas (ROMPCO)", "ZA")),
    ("montepuez", ("Gemfields (Montepuez Rubies)", "GB")),
    ("montepuz rubi", ("Gemfields (Montepuez Rubies)", "GB")),
    ("videocom hidrocarbon", ("Videocom Hydrocarbon Holding", "MZ", False)),

    # ── Madagascar (MDG) — Ambatovy (Sumitomo+Korea+Sherritt), QMM (Rio Tinto), WISCO (CN) ──
    ("ambatovy", ("Sumitomo / Korea Resources / Sherritt (Ambatovy)", "JP")),
    ("dynatec madagascar", ("Sumitomo (Dynatec / Ambatovy)", "JP")),
    ("qit madagascar", ("Rio Tinto (QMM)", "GB")),
    ("madagascar mineral", ("Rio Tinto (QMM affiliates)", "GB")),
    ("wisco", ("Wuhan Iron & Steel (WISCO)", "CN")),
    ("guangxin kam wah", ("WISCO Guangxin Kam Wah", "CN")),
    ("mainland mining", ("Mainland Mining", "CN")),
    ("madagascar oil", ("Madagascar Oil Plc", "GB")),
    ("kraoma", ("KRAOMA (MDG state)", "MG", False)),
    ("pam madagascar", ("PAM Madagascar (Sherritt/Sumitomo)", "JP")),
    ("prochimad", ("Prochimad (DSM)", "NL")),

    # ── Mali (MLI) — Barrick gold, AngloGold, Resolute ──
    ("somilo", ("Barrick (Loulo SOMILO)", "CA")),
    ("yatela", ("AngloGold Ashanti / IAMGOLD (Yatela)", "ZA")),
    ("semos", ("AngloGold Ashanti (Sadiola SEMOS)", "ZA")),
    ("segala mining", ("AngloGold Ashanti (Ségala)", "ZA")),
    ("somisy", ("Resolute Mining (Syama SOMISY)", "GB")),
    ("semico", ("Wassoul'Or (SEMICO)", "ML", False)),
    ("somifi", ("African Petroleum (SOMIFI)", "GB")),

    # ── Burkina Faso (BFA) — Nordgold, Endeavour, Roxgold, Iamgold ──
    ("taparko", ("Nordgold (Taparko SOMITA)", "RU")),
    ("somita", ("Nordgold (Taparko SOMITA)", "RU")),
    ("belahouro", ("Nordgold (Bissa SMB)", "RU")),
    ("societe des mines de belahouro", ("Nordgold (Bissa SMB)", "RU")),
    ("kalsaka mining", ("Amara Mining (Kalsaka)", "GB")),
    ("burkina mining company", ("Nordgold (Bissa)", "RU")),
    ("riverstone karma", ("Riverstone Karma (Volta Resources)", "CA")),
    ("wahgnion", ("Endeavour Mining (Wahgnion)", "GB")),
    ("bouere dohoun gold", ("Roxgold (Bouéré-Dohoun)", "CA")),

    # ── Sierra Leone (SLE) — Tonkolili, Marampa, Koidu, London Mining ──
    ("african minerals", ("African Minerals (Tonkolili)", "GB")),
    ("marampa mines", ("London Mining (Marampa)", "GB")),
    ("koidu", ("Octéa Diamonds (Koidu)", "GB")),
    ("london mining", ("London Mining", "GB")),

    # ── Senegal (SEN) — Endeavour, Eramet, IAMGOLD, Indorama ──
    ("sabodala", ("Endeavour Mining (Sabodala)", "GB")),
    ("petowal mining", ("B2Gold (Mako, ex-Toro Gold)", "CA")),
    ("grande cote", ("Eramet (TiZir Grande Côte)", "FR")),
    ("grande côte", ("Eramet (TiZir Grande Côte)", "FR")),
    ("industries chimiques du senegal", ("ICS (Indorama)", "IN")),
    ("ics ", ("ICS (Indorama)", "IN")),

    # ── Guinea (GIN) — Rio Tinto Simandou, AngloGold Siguiri, Chinese bauxite ──
    ("simfer", ("Rio Tinto (Simfer Simandou)", "GB")),
    ("compagnie des bauxites de kindia", ("CBK (state)", "GN", False)),
    ("dinguiraye", ("Nordgold (Lefa SMD)", "RU")),
    ("chalco guinea", ("Chinalco / Chalco", "CN")),
    ("compagnie du developpement des mines", ("Henan Chine Mining", "CN")),

    # ── Tanzania (TZA) — Ophir, Resolute, Acacia, Shanta, M&P, state TPDC ──
    ("ophir tanzania", ("Ophir Energy (Tanzania)", "GB")),
    ("resolute tanzania", ("Resolute Mining (Golden Pride)", "GB")),
    ("pangea minerals", ("Barrick / Acacia (Pangea)", "CA")),
    ("shanta mining", ("Shanta Gold", "GB")),
    ("panafrican energy tanzania", ("Maurel & Prom (Songo Songo)", "FR")),
    ("m p exploration production tanzania", ("Maurel & Prom (M&P)", "FR")),
    ("tanzania petroleum development", ("TPDC (state)", "TZ", False)),

    # ── Ethiopia (ETH) — MIDROC, Poly-GCL, Dangote, Delonex ──
    ("midroc", ("MIDROC (Al Amoudi)", "SA")),
    ("midrock", ("MIDROC (Al Amoudi)", "SA")),
    ("poly gcl", ("Poly-GCL Petroleum", "CN")),
    ("dangote", ("Dangote Industries", "NG")),
    ("delonex", ("Delonex Energy", "GB")),
    ("newage ethiopia", ("New Age Energy", "GB")),

    # ── Togo (TGO) — SNPT (state), HeidelbergCement, WACEM ──
    ("societe nouvelle des phosphates du togo", ("SNPT (state)", "TG", False)),
    ("snpt", ("SNPT (state)", "TG", False)),
    ("scantogo", ("HeidelbergMaterials (Scantogo)", "DE")),
    ("wacem", ("WACEM (Heidelberg / Diamond Cement)", "IN")),
    ("bb eau vitale", ("Eau Vitale (BB)", "TG", False)),

    # ── Mauritania (MRT) — First Quantum + state ──
    ("mauritanian copper mines", ("First Quantum (MCM Guelb Moghrein)", "CA")),
    ("mauritarian copper mines", ("First Quantum (MCM Guelb Moghrein)", "CA")),
    ("mcm ", ("First Quantum (MCM)", "CA")),
    ("societe mauritanienne des hydrocarbures", ("SMHPM (state)", "MR", False)),
    ("smhpm", ("SMHPM (state)", "MR", False)),
    ("dolphin geophysical", ("Dolphin Geophysical (defunct)", "NO")),
    ("capricorn", ("Capricorn Energy (ex-Cairn)", "GB")),

    # ── Iraq (IRQ) — oil traders (huge magnitudes from SOMO sales) ──
    ("unipec", ("Sinopec UNIPEC", "CN")),
    ("totsa", ("TotalEnergies Trading (TOTSA)", "FR")),
    ("total oil trading", ("TotalEnergies Trading (TOTSA)", "FR")),
    ("indian oil", ("Indian Oil Corporation", "IN")),
    ("jx nippon", ("ENEOS / JX Nippon", "JP")),
    ("toyota tsusho", ("Toyota Tsusho", "JP")),
    ("petro diamond", ("Mitsubishi (Petro-Diamond)", "JP")),

    # ── Nigeria (NGA) — state vehicles, NLNG, Chevron ──
    ("nigeria petroleum development", ("NPDC (NNPC subsidiary)", "NG", False)),
    ("nigerian petroleum development", ("NPDC (NNPC subsidiary)", "NG", False)),
    ("nnpc crude oil marketing", ("NNPC COMD", "NG", False)),
    ("nigeria liquefied natural gas", ("NLNG (NNPC + Shell + Total + Eni)", "NG", False)),
    ("nlng", ("NLNG", "NG", False)),
    ("star deep water", ("Chevron Nigeria (Star Deep)", "US")),

    # ── Indonesia (IDN) — INPEX, Adaro, Medco, Kideco, Premier ──
    ("indonesia petroleum", ("INPEX", "JP")),
    ("virginia indonesia", ("ConocoPhillips Indonesia (Vico)", "US")),
    ("premier oil natuna", ("Harbour Energy (Premier Oil)", "GB")),
    ("adaro", ("Adaro Energy Indonesia", "ID")),
    ("medco e p", ("Medco Energi", "ID")),
    ("medco e&p", ("Medco Energi", "ID")),
    ("kideco", ("Kideco Jaya Agung (Indika Energy)", "ID")),

    # ── Norway (NOR) — variants of major operators ──
    ("statoilhydro", ("Equinor", "NO")),
    ("dong e p", ("Ørsted (DONG E&P)", "DK")),
    ("idemitsu", ("Idemitsu Kosan", "JP")),
    ("gdf suez", ("ENGIE (GDF Suez)", "FR")),
    ("centrica", ("Centrica", "GB")),
    ("sval energi", ("Sval Energi (HitecVision)", "NO")),
    ("solveig gas", ("Solveig Gas Norway", "NO")),
    ("exxonmobile", ("ExxonMobil", "US")),

    # ── Kazakhstan (KAZ) — TengizChevroil, Karachaganak JV, KMG subsidiaries ──
    ("tengizchevroil", ("TengizChevroil (Chevron 50%)", "US")),
    ("tengizshevroil", ("TengizChevroil (Chevron 50%)", "US")),
    ("тенгизшевройл", ("TengizChevroil (Chevron 50%)", "US")),
    ("karachaganak", ("Karachaganak (Eni operator)", "IT")),
    ("карачаганак петролиум", ("Karachaganak Petroleum Operating (Eni operator)", "IT")),
    ("mangistau", ("MangistauMunaiGas (KMG)", "KZ", False)),
    ("cnpc aktobe", ("CNPC AktobeMunaiGas", "CN")),
    ("kazgermunai", ("KazGerMunai (CNPC/KMG)", "CN")),
    ("kazchrome", ("Eurasian Resources (Kazchrome)", "LU")),
    ("kazzinc", ("Glencore (Kazzinc)", "CH")),

    # ── Mongolia (MNG) — state + Rio Tinto Oyu Tolgoi ──
    ("erdenet mining", ("Erdenet Mining (state)", "MN", False)),
    ("erdenes tavan tolgoi", ("Erdenes Tavan Tolgoi (state)", "MN", False)),
    ("oyu tolgoi", ("Rio Tinto (Oyu Tolgoi)", "GB")),
    ("tavantolgoi", ("Erdenes Tavan Tolgoi (state)", "MN", False)),

    # ── Ukraine (UKR) — Naftogaz subsidiaries (state) and iron ore enrichment ──
    ("ukrgazvydobuvannia", ("Ukrgazvydobuvannya (Naftogaz)", "UA", False)),
    ("naftogazvydobuvannia", ("Naftogazvydobuvannya", "UA", False)),
    ("ukrnaftoburinnia", ("Ukrnaftoburinnia", "UA", False)),
    ("iron ore enrichment", ("Iron Ore Enrichment Works (Metinvest)", "UA")),
    ("southern mining factory", ("Southern Mining (Metinvest)", "UA")),

    # ── Cameroon (CMR) — SNH already covered via "societe nationale des hydrocarbures";
    # add bare SNH and SNH-Mandate / SNH-Fonctionnement variants explicitly
    ("snh fonctionnement", ("SNH (state)", "CM", False)),
    ("snh mandate", ("SNH (state)", "CM", False)),
    ("pecten cameroun", ("Shell Cameroon (Pecten, sold)", "GB")),
    ("cameroon oil transportation", ("COTCO (ExxonMobil/Petronas/Chad)", "US", False)),
    ("apcc", ("Addax Petroleum Cameroon", "CN")),

    # ── Colombia (COL) — Cerrejón, Drummond, Pacific, Occidental, Glencore Prodeco ──
    ("cerrejon", ("Glencore (Cerrejón, sole owner from 2022)", "CH")),
    ("drummond", ("Drummond Coal", "US")),
    ("pacific exploration", ("Frontera Energy (Pacific Exploration)", "CA")),
    ("occidental", ("Occidental Petroleum (Oxy)", "US")),
    ("grupo prodeco", ("Glencore (Prodeco)", "CH")),
    ("gran tierra", ("Gran Tierra Energy", "CA")),

    # ── Peru (PER) — Southern Peru Copper (Grupo México) ──
    ("southern peru copper", ("Grupo México (Southern Copper)", "MX")),
    ("hunt oil company of peru", ("Hunt Oil", "US")),

    # ── Ecuador (ECU) — Tongling/CRCC Chinese miners, Lundin Gold ──
    ("ecuacorriente", ("Tongling/CRCC (Mirador)", "CN")),
    ("explorcobres", ("Tongling/CRCC (San Carlos Panantza)", "CN")),
    ("dpmecuador", ("Lumina Gold", "CA")),
    ("aurelian ecuador", ("Lundin Gold (Aurelian)", "CA")),
    ("novomining", ("Codelco / Novomining JV", "CL")),
    ("odin mining", ("Odin Mining", "CA")),

    # ── Republic of Congo (COG) — TotalEnergies Congorep + Perenco + CMS Nomeco ──
    ("congorep", ("TotalEnergies (CONGOREP)", "FR")),
    ("cms nomeco", ("CMS Energy / Nuevo Energy", "US")),
    ("nuevo congo", ("Nuevo Energy Congo", "US")),
    ("murphy west africa", ("Murphy Oil (West Africa)", "US")),
    ("philia ", ("Philia (commodities trader)", "CH")),

    # ── Myanmar (MMR) — Daewoo, Posco, Petronas Carigali, gas transportation ──
    ("daewoo international", ("Posco International (Daewoo)", "KR")),
    ("posco daewoo", ("Posco International", "KR")),
    ("pc myanmar", ("Petronas Carigali (Myanmar)", "MY")),
    ("moattama gas", ("Moattama Gas Transportation (consortium)", "MM", False)),
    ("taninthayi pipeline", ("Taninthayi Pipeline (consortium)", "MM", False)),

    # ── PNG (Papua New Guinea) — Kumul, Ok Tedi, state ──
    ("kumul petroleum", ("Kumul Petroleum (PNG state)", "PG", False)),
    ("ok tedi", ("Ok Tedi Mining (PNG state)", "PG", False)),
    ("mineral resources cmca", ("CMCA / OK Tedi (state)", "PG", False)),
    ("npcp", ("National Petroleum Co PNG (state)", "PG", False)),

    # ── 2026-05-15 BATCH 2: cover the remaining sub-80% countries.
    # IMPORTANT: normalise() strips parens content *before* matching, so
    # for names like "Societe Nationale d'Operations Petrolieres (PETROCI)"
    # the acronym is gone — use the DESCRIPTIVE form as the override key.

    # ── ARM (Armenia) — copper-molybdenum, Russian-controlled ──
    ("zangezur", ("Zangezur Copper-Molybdenum (Vallex/CRONIMET/GeoProMining)", "RU")),
    ("zangezour", ("Zangezur Copper-Molybdenum", "RU")),
    ("geopromining", ("GeoProMining Gold", "RU")),
    ("teghout", ("Teghout (Vallex)", "RU")),
    ("chaarat kapan", ("Chaarat Gold Holdings", "GB")),
    ("agarak copper molybdenum", ("Agarak Copper-Molybdenum (state)", "AM", False)),
    ("lydian armenia", ("Lydian International (suspended)", "CA")),

    # ── HND (Honduras) — cement + Canadian miners ──
    ("cementos del norte", ("Cementos del Norte (local)", "HN", False)),
    ("minerales de occidente", ("Aura Minerals (San Andrés)", "CA")),
    ("american pacific honduras", ("American Pacific Resources", "US")),

    # ── TJK (Tajikistan) — Chinese-state JVs ──
    ("zarafshan", ("Zarafshon (China Nonferrous JV)", "CN")),
    ("zarafshon", ("Zarafshon (China Nonferrous JV)", "CN")),
    ("pakrut", ("Pakrut Gold (Zijin)", "CN")),
    ("tajik chinese mining", ("Tajik-Chinese Mining JV", "CN")),
    ("huaksin gayur cement", ("Huaxin Gayur Cement", "CN")),

    # ── ALB (Albania) — Geo-Jade, Kurum, state vehicles ──
    ("bankers petroleum", ("Geo-Jade Petroleum (Bankers)", "CN")),
    ("kurum international", ("Kurum Holding", "TR")),
    ("kesh ", ("KESH (state power)", "AL", False)),
    ("albpetrol", ("Albpetrol (state)", "AL", False)),
    ("stream oil", ("Stream Oil & Gas (defunct US)", "US")),

    # ── KGZ (Kyrgyzstan) — Centerra Gold (Kumtor), Zijin, KAZ Minerals ──
    ("kumtor", ("Centerra Gold (Kumtor, nationalised 2022)", "CA")),
    ("altynken", ("Zijin Mining (Altynken)", "CN")),
    ("kaz minerals bozymchak", ("KAZ Minerals (Bozymchak)", "GB")),

    # ── CIV (Côte d'Ivoire) — PETROCI (descriptive), Foxtrot, Endeavour ──
    ("societe nationale operations petrolieres", ("PETROCI (state)", "CI", False)),
    ("operations petrolieres cote ivoire", ("PETROCI (state)", "CI", False)),
    ("foxtrot international", ("Foxtrot Petroleum / SECI", "MU")),
    ("agbaou gold", ("Endeavour Mining (Agbaou, sold Allied)", "AU")),
    ("autres acheteurs", ("Other buyers (aggregate)", "CI", False)),

    # ── SUR (Suriname) — Rosebel (IAMGOLD→Zijin), state ──
    ("rosebel gold", ("IAMGOLD/Zijin (Rosebel)", "CN")),
    ("staatsolie", ("Staatsolie Suriname (state)", "SR", False)),
    ("grassalco", ("NV Grassalco (state)", "SR", False)),

    # ── AFG (Afghanistan) — Aynak (MCC China), state ──
    ("aynak", ("MCC China (Aynak Copper)", "CN")),
    ("jcl aynak", ("MCC China (Aynak Copper)", "CN")),
    ("northern coal enterprise", ("Northern Coal (state)", "AF", False)),
    ("afghan gas enterprise", ("Afghan Gas (state)", "AF", False)),

    # ── MWI (Malawi) — Paladin uranium, Indian timber ──
    ("paladin africa", ("Paladin Energy (Kayelekera)", "AU")),
    ("raiply malawi", ("Raiply (Indian timber)", "IN")),
    ("vizara plantation", ("Vizara (local)", "MW", False)),

    # ── LBR (Liberia) — ArcelorMittal, NOCAL, China Union, Firestone ──
    ("arcelor mittal", ("ArcelorMittal", "LU")),
    ("nocal", ("NOCAL (state)", "LR", False)),
    ("national oil company of liberia", ("NOCAL (state)", "LR", False)),
    ("firestone liberia", ("Bridgestone (Firestone)", "JP")),
    ("china union", ("China Union (Bong Mines)", "CN")),
    ("oranlo petroleum", ("Oranto / Atlas Oranto", "NG", False)),
    ("oranto petroleum", ("Atlas Oranto", "NG", False)),

    # ── GTM (Guatemala) — Pan American Silver (Tahoe), Solway ──
    ("minera san rafael", ("Pan American Silver (Escobal)", "CA")),
    ("montana exploradora", ("Pan American Silver / Tahoe (Marlin)", "CA")),
    ("compania guatemalteca de niquel", ("Solway (CGN Fenix)", "CH")),

    # ── SLE (Sierra Leone) — additional ──
    ("kingho mining", ("Kingho Mining (Tonkolili)", "CN")),
    ("kingho investment", ("Kingho Investment", "CN")),
    ("sierra minerals", ("Vimetco (Sierra Minerals)", "NL")),
    ("talisman sierra leone", ("Talisman Energy (defunct)", "CA")),
    ("minexco", ("Minexco (local)", "SL", False)),

    # ── STP (São Tomé) — small operators ──
    ("equator exploration", ("Equator Exploration (Vaalco)", "US")),
    ("sinoangol", ("Sinopec-Sonangol JV", "CN")),
    ("galp energy stp", ("Galp Energia (STP)", "PT")),
    ("galp energia stp", ("Galp Energia (STP)", "PT")),

    # ── ARG (Argentina) — Barrick/Shandong, AngloGold, Vista, Glencore ──
    ("minera andina del sol", ("Barrick / Shandong Gold (Veladero)", "CN")),
    ("cerro vanguardia", ("AngloGold Ashanti (Cerro Vanguardia)", "ZA")),
    ("vista oil", ("Vista Energy (Argentina)", "AR")),
    ("vista energy", ("Vista Energy", "AR")),
    ("minera alumbrera", ("Glencore/Yamana (Alumbrera)", "CH")),

    # ── DEU (Germany) — Wintershall DEA, RWE, BEB Shell+Exxon ──
    ("beb erdgas", ("BEB (Shell + ExxonMobil JV)", "GB")),
    ("dea deutsche erdoel", ("Wintershall DEA Deutschland", "DE")),
    ("dea deutsche erdol", ("Wintershall DEA Deutschland", "DE")),
    ("rwe power", ("RWE", "DE")),
    ("rwe gruppe", ("RWE", "DE")),
    ("sudwestdeutsche salzwerke", ("Südwestdeutsche Salzwerke", "DE")),

    # ── MNG (Mongolia) — additional Mongolian + Chinese ──
    ("erdenet ", ("Erdenet Mining (state + Rostec)", "MN", False)),
    ("mongolyn alt mak", ("Mongolyn Alt MAK", "MN", False)),
    ("mongol ju yuan", ("Mongol Ju Yuan Li (Chinese)", "CN")),
    ("energy resources llc", ("Energy Resources (MCS Mongolia)", "MN", False)),
    ("energyresources", ("Energy Resources (MCS)", "MN", False)),
    ("boroo gold", ("Centerra Gold (Boroo)", "CA")),
    ("tavan tolgoi jsc", ("Tavan Tolgoi JSC (state)", "MN", False)),

    # ── GAB (Gabon) — Assala (Carlyle), Eramet COMILOG ──
    ("assala", ("Carlyle Group (Assala Energy)", "US")),
    ("comilog", ("Eramet (COMILOG manganese)", "FR")),
    ("compagnie miniere de l ogooue", ("Eramet (COMILOG)", "FR")),
    ("oranje nassau", ("Oranje Nassau Energie", "NL")),
    ("societe equatoriale des mines", ("SEM (state)", "GA", False)),

    # ── PER (Peru) — Glencore Antapaccay/Tintaya, EITI aggregate buckets ──
    ("antapaccay", ("Glencore (Antapaccay)", "CH")),
    ("xstrata tintaya", ("Glencore (ex-Xstrata Tintaya)", "CH")),
    ("companias agregadas", ("Aggregate companies (Peru EITI)", "PE", False)),
    ("companies with aggregate information", ("Aggregate companies (Peru EITI)", "PE", False)),
    ("aggregate companies", ("Aggregate companies (Peru EITI)", "PE", False)),

    # ── KAZ (Kazakhstan) — additional spellings ──
    ("petro kazakhstan kumkol", ("PetroKazakhstan (CNPC)", "CN")),
    ("buzachi operating", ("Buzachi Operating (CNPC+Lukoil)", "CN")),

    # ── PNG (Papua New Guinea) — additional ──
    ("state owned enterprises", ("State-owned (PNG)", "PG", False)),
    ("morobe consolidated goldfields", ("Newcrest (Morobe Goldfields)", "AU")),
    ("mcc ramu nico", ("MCC Ramu Nickel (CMC China)", "CN")),
    ("gas resources gigira", ("ExxonMobil PNG / Oil Search", "US")),
    ("lavana", ("Lavana / PNG MRDC (state)", "PG", False)),

    # ── PHL (Philippines) — PNOC (state), Prime Energy, Galoc ──
    ("philippine national oil", ("PNOC (state)", "PH", False)),
    ("pnoc exploration", ("PNOC Exploration (state)", "PH", False)),
    ("prime energy resources", ("Prime Energy / Total operator", "GB")),
    ("galoc production", ("Galoc Production / Otto Energy", "AU")),
    ("philsaga mining", ("Philsaga / TVI Pacific", "CA")),

    # ── IRQ (Iraq) — oil traders (descriptive names; "(UNIPEC...)" is paren-stripped) ──
    ("china international", ("Sinopec UNIPEC / China International (oil trader)", "CN")),
    ("reliance ", ("Reliance Industries (oil trader)", "IN")),
    ("conoco phillips", ("ConocoPhillips", "US")),
    ("phillips ", ("ConocoPhillips / Phillips 66", "US")),
    ("cepsa", ("CEPSA (Mubadala)", "AE")),

    # ── 2026-05-15 BATCH 3: Cyrillic-form aliases (post-transliteration the
    # normalise() function will produce Latin forms; these keys are in
    # Cyrillic so they're transliterated by the same routine — Cyrillic
    # company names that previously survived as empty strings now match).
    # The keys here are written in Cyrillic; transliteration handles them.
    # ── Tajikistan (TJK) Cyrillic ──
    ("zarafshon", ("Zarafshon (China Nonferrous JV)", "CN")),
    ("hukasin gayur", ("Huaxin Gayur Cement", "CN")),
    ("khuaksin gayur", ("Huaxin Gayur Cement", "CN")),
    ("pakrut", ("Pakrut Gold (Zijin)", "CN")),
    ("anzob", ("Anzob Mining (Tajik-American JV)", "US")),
    ("aprelevka", ("Aprelevka (Tajik-Canadian JV)", "CA")),
    ("fon yagnob", ("Fon-Yagnob (state coal)", "TJ", False)),
    ("angishti tochik", ("Angishti Tochik (state)", "TJ", False)),
    # ── Kazakhstan (KAZ) Cyrillic ──
    ("mangistaumunaigaz", ("MangistauMunaiGas (KMG)", "KZ", False)),
    ("kazakhstanskii filial", ("Karachaganak Petroleum Operating (Eni)", "IT")),
    ("petroleium opereiting", ("Karachaganak Petroleum Operating (Eni)", "IT")),
    ("kazakhgaz", ("KazTransGas (KMG)", "KZ", False)),
    ("kazmunaigaz", ("KazMunaiGas (state)", "KZ", False)),
    # ── Ukraine (UKR) Cyrillic ──
    ("ukrgazvidobuvannia", ("Ukrgazvydobuvannya (Naftogaz)", "UA", False)),
    ("naftogazvidobuvannia", ("Naftogazvydobuvannya", "UA", False)),
    # ── Kyrgyzstan (KGZ) Cyrillic ──
    ("kumtor gold", ("Centerra Gold (Kumtor)", "CA")),
    ("altynken", ("Zijin Mining (Altynken)", "CN")),
    ("kaz minerals bozymchak", ("KAZ Minerals (Bozymchak)", "GB")),

    # ── 2026-05-15 BATCH 4: French-d forms (where "d'Operations" survives
    # normalisation as "D OPERATIONS" because bare "d" isn't a legal token)
    # ── CIV PETROCI variants ──
    ("societe nationale d operations petrolieres", ("PETROCI (state)", "CI", False)),
    ("operations petrolieres cote d ivoire", ("PETROCI (state)", "CI", False)),
    ("nationale d operations petrolieres", ("PETROCI (state)", "CI", False)),
    ("ste mines tongon", ("Barrick Gold (Tongon)", "CA")),
    ("lgl mines ci", ("LGL Mines CI", "CI", False)),
    ("newcrest hire", ("Newcrest Mining", "AU")),

    # ── TJK Russian-transliterated additions ──
    ("tadzhiksko kitaiskaia", ("Tajik-Chinese Mining (China Nonferrous)", "CN")),
    ("tadzhikskii metalurgicheskii", ("Tajik Metallurgical Plant (state)", "TJ", False)),
    ("sementi tochik", ("Cementi Tochik (state cement)", "TJ", False)),
    ("semanti tojik", ("Cementi Tochik (state cement)", "TJ", False)),
    ("bohtar operating", ("Bohtar Operating (Total/CNPC)", "FR")),

    # ── MWI placeholders + small operators ──
    ("aggregated companies not submitting", ("Aggregated companies (Malawi EITI)", "MW", False)),
    ("terrastone", ("Terrastone (local)", "MW", False)),
    ("optichem", ("Optichem (Malawi)", "MW", False)),
    ("rakgas", ("RAKGAS (UAE)", "AE")),
    ("mota engil", ("Mota-Engil", "PT")),

    # ── SLE additional ──
    ("other mining companies", ("Other mining companies (SLE EITI aggregate)", "SL", False)),
    ("s d steel tonkolili", ("Shandong Iron & Steel (Tonkolili)", "CN")),
    ("african petroleum", ("African Petroleum Corp", "AU")),
    ("a z petroleum", ("A-Z Petroleum", "SL", False)),

    # ── LBR additional ──
    ("elenilto", ("Elenilto Minerals", "IL")),
    ("mng gold liberia", ("MNG Gold (Turkish)", "TR")),
    ("mng gold exploration", ("MNG Gold (Turkish)", "TR")),
    ("liberia agricultural", ("Liberian Agricultural Company (rubber)", "LR", False)),
    ("liberian agricultural", ("Liberian Agricultural Company (rubber)", "LR", False)),
    ("putu iron ore", ("Severstal / Putu Iron Ore", "RU")),

    # ── GTM additional ──
    ("cgn ", ("Solway (CGN Fenix Nickel)", "CH")),
    (" cgn", ("Solway (CGN Fenix Nickel)", "CH")),
    ("guaxilan", ("Guaxilán (local)", "GT", False)),
    ("city peten", ("City Petén Oil", "US")),
    ("pena rubia", ("Peña Rubia (local)", "GT", False)),
    ("silice centroamerica", ("Silice de Centroamerica (local)", "GT", False)),
    ("maya niquel", ("Maya Niquel (local)", "GT", False)),
]
# normalise to (norm_substring, canonical_name, hq_iso2, is_filer)
OVERRIDES = []
for k, v in _OVR:
    name, hq = v[0], v[1]
    flag = v[2] if len(v) > 2 else None
    OVERRIDES.append((k, name, hq, flag))

LEGAL_TOKENS = {
    "sa", "sas", "sasu", "sarl", "sarlu", "sau", "spa", "srl", "ltd", "limited", "plc", "llc", "llp",
    "inc", "incorporated", "corp", "corporation", "co", "company", "cia", "gmbh", "ag", "kg", "nv", "bv",
    "ab", "as", "asa", "oy", "oyj", "ojsc", "pjsc", "jsc", "oao", "zao", "pao", "pty", "pvt", "ltda",
    "eurl", "gie", "sca", "scs", "snc", "se", "kk", "kgaa", "lp", "ulc", "unltd", "pc", "pllc",
    "doo", "dd", "ad", "ead", "tov", "too", "ip", "pe", "fze", "fzco", "wll", "lda", "scarl", "scrl",
    "the", "of", "and", "for", "de", "du", "des", "la", "le", "les", "el", "der", "die", "das", "y",
}
GENERIC_WORDS = {
    "mining", "mines", "mine", "minerals", "mineral", "oil", "gas", "petroleum", "petrole", "petroleos",
    "energy", "energie", "energia", "resources", "resource", "exploration", "production", "development",
    "international", "group", "holdings", "holding", "company", "industries", "industrial", "metals",
    "metal", "gold", "copper", "iron", "coal", "diamond", "diamonds", "national", "africa", "african",
    "global", "ventures", "venture", "trading", "trade", "general", "limited", "societe",
    "compania", "compagnie", "enterprises", "enterprise", "services", "operations", "joint",
}


# Cyrillic → Latin transliteration table (GOST 7.79-2000 System B / common scientific).
# Applied before NFKD/ASCII-ignore so Russian/Ukrainian/Kazakh names survive normalisation.
# Without this step EITI rows from TJK/KAZ/KGZ/UKR/RUS in Cyrillic-only get dropped.
_CYRILLIC_MAP = {
    "А":"A","Б":"B","В":"V","Г":"G","Д":"D","Е":"E","Ё":"E","Ж":"ZH","З":"Z",
    "И":"I","Й":"I","К":"K","Л":"L","М":"M","Н":"N","О":"O","П":"P","Р":"R",
    "С":"S","Т":"T","У":"U","Ф":"F","Х":"KH","Ц":"TS","Ч":"CH","Ш":"SH","Щ":"SHCH",
    "Ъ":"","Ы":"Y","Ь":"","Э":"E","Ю":"YU","Я":"YA",
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z",
    "и":"i","й":"i","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r",
    "с":"s","т":"t","у":"u","ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch",
    "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
    # Additional letters used in Kazakh / Tajik / Kyrgyz / Ukrainian
    "Ә":"AE","Ғ":"GH","Қ":"Q","Ң":"NG","Ө":"OE","Ұ":"U","Ү":"UE","Һ":"H","І":"I","Ї":"I","Є":"YE","Ҷ":"J","Ҳ":"H","Ӣ":"I","Ӯ":"U","Қ":"Q",
    "ә":"ae","ғ":"gh","қ":"q","ң":"ng","ө":"oe","ұ":"u","ү":"ue","һ":"h","і":"i","ї":"i","є":"ye","ҷ":"j","ҳ":"h","ӣ":"i","ӯ":"u",
}
_CYRILLIC_TRANS = str.maketrans(_CYRILLIC_MAP)


def normalise(name):
    if not name:
        return ""
    s = str(name).translate(_CYRILLIC_TRANS)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").upper()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return " ".join(t for t in s.split() if t.lower() not in LEGAL_TOKENS).strip()


def to_iso3(iso2):
    if not iso2:
        return ""
    iso2 = str(iso2).strip().upper()
    if len(iso2) == 3:
        return iso2
    fix = {"XK": "XKX", "KV": "XKX"}
    if iso2 in fix:
        return fix[iso2]
    try:
        c = pycountry.countries.get(alpha_2=iso2)
        return c.alpha_3 if c else ""
    except Exception:
        return ""


def is_anchor(norm):
    words = norm.split()
    ng = [w for w in words if w.lower() not in GENERIC_WORDS]
    return (len(words) >= 2 and len(ng) >= 1) or (len(words) == 1 and len(words[0]) >= 5 and words[0].lower() not in GENERIC_WORDS)


def main():
    # ── 1. load Orbis universe; index by entity country ──
    # rows: bvd_id,name,entity_country,nace_core,n_subsidiaries,guo_bvd_id,guo_name,guo_type,guo_country,peak_operating_revenue_th_usd,in_cbcr_universe
    by_country_norm = defaultdict(lambda: defaultdict(list))   # iso3 -> norm -> [cand]
    global_norm = defaultdict(list)                            # norm -> [cand]   (only in_cbcr_universe entities, for the global fallback)
    n_ent = 0
    with open(UNIVERSE, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            nm = normalise(r["name"])
            if not nm:
                continue
            n_ent += 1
            ec3 = to_iso3(r["entity_country"]) or r["entity_country"].strip().upper()
            gc2 = (r["guo_country"] or r["entity_country"] or "").strip()
            cand = {"bvd_id": r["bvd_id"], "orbis_name": r["name"], "guo_name": r.get("guo_name", ""),
                    "guo_type": r.get("guo_type", ""), "hq_iso3": to_iso3(gc2),
                    "in_cbcr_universe": (str(r.get("in_cbcr_universe", "")).strip() in ("1", "True", "true")),
                    "n_subs": r.get("n_subsidiaries", ""), "rev": r.get("peak_operating_revenue_th_usd", "")}
            by_country_norm[ec3][nm].append(cand)
            if cand["in_cbcr_universe"]:
                global_norm[nm].append(cand)
    # per-country anchor lists (longest first) for substring matching
    country_anchors = {c: sorted((n for n in norms if is_anchor(n)), key=lambda s: (-len(s.split()), -len(s)))
                       for c, norms in by_country_norm.items()}
    global_anchors = sorted((n for n in global_norm if is_anchor(n)), key=lambda s: (-len(s.split()), -len(s)))
    print(f"Orbis universe: {n_ent:,} named entities in {len(by_country_norm)} countries; {len(global_norm):,} distinct in-CbCR-universe names for the global fallback")

    def pick(cands):
        # prefer an in-CbCR-universe candidate (the real MNE parent), then the one with most subsidiaries
        mne = [c for c in cands if c["in_cbcr_universe"]]
        pool = mne or cands
        def nsub(c):
            try:
                return int(c["n_subs"])
            except (ValueError, TypeError):
                return -1
        return max(pool, key=nsub)

    # ── 2. distinct EITI (source iso3, company) with value weight ──
    eiti = defaultdict(lambda: {"n_rows": 0, "value_usd": 0.0})
    with open(EITI_PAY, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k = (r["iso3"], r["company_name"])
            eiti[k]["n_rows"] += 1
            v = r.get("value_usd", "")
            if v:
                try:
                    eiti[k]["value_usd"] += float(v)
                except ValueError:
                    pass
    print(f"Distinct (source country, EITI company): {len(eiti):,}")

    ovr = sorted(((normalise(k), name, hq, flag) for k, name, hq, flag in OVERRIDES if normalise(k)), key=lambda t: -len(t[0]))

    # ── 3. match ──
    out_rows = []
    counts = defaultdict(int)
    norm_cache = {}
    for (iso3, company), w in sorted(eiti.items()):
        q = norm_cache.get(company)
        if q is None:
            q = normalise(company)
            norm_cache[company] = q
        q_pad = " " + q + " " if q else " "
        m = None   # dict: bvd_id, orbis_name, guo_name, guo_type, hq_iso3, in_cbcr_universe, score, method
        if not q:
            pass
        elif (oh := next(((kn, name, hq, flag) for kn, name, hq, flag in ovr if " " + kn + " " in q_pad), None)):
            kn, name, hq, flag = oh
            hq3 = to_iso3(hq)
            # if the override didn't fix the filer flag, try to learn it from the Orbis universe by the canonical name
            in_u = flag
            if in_u is None:
                gn = normalise(name)
                cl = global_norm.get(gn) or by_country_norm.get(hq3, {}).get(gn)
                in_u = bool(cl and pick(cl)["in_cbcr_universe"])
                in_u = in_u or True   # overrides are major operators → default True if not found
            m = {"bvd_id": "", "orbis_name": name, "guo_name": name, "guo_type": "", "hq_iso3": hq3,
                 "in_cbcr_universe": bool(in_u), "score": 99.0, "method": "override"}
            counts["override"] += 1
        else:
            cn = by_country_norm.get(iso3, {})
            ca = country_anchors.get(iso3, [])
            if q in cn:
                c = pick(cn[q]); m = dict(c, score=100.0, method="exact_norm_country")
            elif (hit := next((g for g in ca if " " + g + " " in q_pad), None)):
                c = pick(cn[hit]); m = dict(c, score=95.0, method="substring_country")
            elif cn and (res := process.extractOne(q, list(cn.keys()), scorer=fuzz.token_sort_ratio, score_cutoff=FUZZY_THRESHOLD)):
                c = pick(cn[res[0]]); m = dict(c, score=float(res[1]), method="fuzzy_country")
            elif q in global_norm:
                c = pick(global_norm[q]); m = dict(c, score=100.0, method="exact_norm_global")
            elif (hit := next((g for g in global_anchors if " " + g + " " in q_pad), None)):
                c = pick(global_norm[hit]); m = dict(c, score=95.0, method="substring_global")
            if m is not None:
                counts[m["method"]] += 1
        if m is None:
            counts["unmatched"] += 1
            out_rows.append({"source_iso3": iso3, "company_name": company, "company_norm": q, "n_payment_rows": w["n_rows"],
                             "total_value_usd": f"{w['value_usd']:.2f}", "matched_orbis_name": "", "matched_bvd_id": "",
                             "matched_guo_name": "", "guo_type": "", "hq_iso3": "", "in_cbcr_universe": "",
                             "match_score": "", "match_method": "unmatched"})
        else:
            out_rows.append({"source_iso3": iso3, "company_name": company, "company_norm": q, "n_payment_rows": w["n_rows"],
                             "total_value_usd": f"{w['value_usd']:.2f}", "matched_orbis_name": m.get("orbis_name", ""),
                             "matched_bvd_id": m.get("bvd_id", ""), "matched_guo_name": m.get("guo_name", ""), "guo_type": m.get("guo_type", ""),
                             "hq_iso3": m.get("hq_iso3", ""), "in_cbcr_universe": int(bool(m.get("in_cbcr_universe", False))),
                             "match_score": f"{m['score']:.0f}", "match_method": m["method"]})

    cols = ["source_iso3", "company_name", "company_norm", "n_payment_rows", "total_value_usd",
            "matched_orbis_name", "matched_bvd_id", "matched_guo_name", "guo_type", "hq_iso3", "in_cbcr_universe", "match_score", "match_method"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w_ = csv.DictWriter(f, fieldnames=cols)
        w_.writeheader()
        for r in out_rows:
            w_.writerow(r)

    # ── 4. coverage report ──
    def vf(rows):
        return sum(float(r["total_value_usd"]) for r in rows)
    tot_v = vf(out_rows)
    matched = [r for r in out_rows if r["match_method"] != "unmatched"]
    mne = [r for r in matched if str(r["in_cbcr_universe"]) == "1"]
    dom = [r for r in matched if r["hq_iso3"] and r["hq_iso3"] == r["source_iso3"]]
    dom_mne = [r for r in dom if str(r["in_cbcr_universe"]) == "1"]
    n = len(out_rows); nm = len(matched)
    print(f"\nWrote {OUT}: {n:,} (source, company) rows.")
    print(f"  matched: {nm:,} ({100*nm/n:.0f}% of names) — " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"  value matched to an Orbis entity: ${vf(matched)/1e9:,.1f} B of ${tot_v/1e9:,.1f} B ({100*vf(matched)/tot_v:.0f}% by value)")
    print(f"  of matched value: in CbCR universe ${vf(mne)/1e9:,.1f} B | not ${ (vf(matched)-vf(mne))/1e9:,.1f} B")
    print(f"  domestic (hq==source): ${vf(dom)/1e9:,.1f} B, of which in CbCR universe ${vf(dom_mne)/1e9:,.1f} B (the rest of the domestic slice is dropped in 1_8)")
    fhq = defaultdict(float)
    for r in matched:
        if r["hq_iso3"] and r["hq_iso3"] != r["source_iso3"]:
            fhq[r["hq_iso3"]] += float(r["total_value_usd"])
    print("  top foreign-HQ countries by matched value ($B): " + ", ".join(f"{k} {v/1e9:,.0f}" for k, v in sorted(fhq.items(), key=lambda kv: -kv[1])[:15]))


if __name__ == "__main__":
    main()
