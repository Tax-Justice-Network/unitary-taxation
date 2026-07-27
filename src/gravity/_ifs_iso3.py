# IMF IFS numeric country code -> ISO3, for mapping CDIS/CPIS counterpart codes
# (COMP_BREAKDOWN_1 = "IMF_CNT_COUNTRY_<n>"). Standard IMF IFS / BOP area codes.
# Spot-checks validated at runtime in build_features (122=AUT, 134=DEU, 132=FRA,
# 111=USA, 136=ITA, 158=JPN, 924=CHN, 534=IND). Unmapped codes are logged.

IFS_TO_ISO3 = {
    111: "USA", 112: "GBR", 122: "AUT", 124: "BEL", 126: "BGR", 128: "DNK",
    132: "FRA", 134: "DEU", 136: "ITA", 137: "LUX", 138: "NLD", 142: "NOR",
    144: "SWE", 146: "CHE", 156: "CAN", 158: "JPN", 172: "FIN", 174: "GRC",
    176: "ISL", 178: "IRL", 181: "MLT", 182: "PRT", 184: "ESP", 186: "TUR",
    193: "AUS", 196: "NZL", 199: "ZAF",
    # Latin America & Caribbean
    213: "ARG", 218: "BOL", 223: "BRA", 228: "CHL", 233: "COL", 238: "CRI",
    243: "DOM", 248: "ECU", 253: "SLV", 258: "GTM", 263: "HTI", 268: "HND",
    273: "MEX", 278: "NIC", 283: "PAN", 288: "PRY", 293: "PER", 298: "URY",
    299: "VEN", 311: "ATG", 313: "BHS", 316: "BRB", 321: "DMA", 328: "GRD",
    336: "GUY", 343: "JAM", 351: "KNA", 352: "BLZ", 353: "LCA", 354: "VCT",
    361: "SUR", 362: "TTO", 364: "ABW",
    # Middle East / North Africa / Central Asia
    419: "BHR", 423: "CYP", 429: "IRN", 433: "IRQ", 436: "ISR", 439: "JOR",
    443: "KWT", 446: "LBN", 449: "OMN", 453: "QAT", 456: "SAU", 459: "SYR",
    463: "ARE", 466: "EGY", 469: "YEM", 472: "AFG", 474: "DZA", 476: "GEO",
    478: "KAZ", 481: "KGZ", 482: "ARM", 485: "AZE", 486: "TJK", 487: "TKM",
    488: "UZB",
    # Sub-Saharan Africa
    616: "AGO", 618: "BWA", 622: "BDI", 624: "CMR", 626: "CPV", 628: "CAF",
    628.5: "TCD", 632: "COM", 634: "COG", 636: "BEN", 638: "GNQ", 642: "ETH",
    643: "GAB", 646: "GMB", 648: "GHA", 652: "GNB", 654: "GIN", 656: "CIV",
    662: "KEN", 664: "LSO", 666: "LBR", 668: "LBY", 672: "MDG", 674: "MWI",
    676: "MLI", 678: "MRT", 682: "MUS", 684: "MAR", 686: "MOZ", 688: "NER",
    692: "NGA", 694: "ZWE", 698: "RWA", 711: "STP", 716: "SEN", 718: "SYC",
    722: "SLE", 724: "SOM", 726: "NAM", 728: "NAM", 732: "SDN", 734: "SWZ",
    738: "TZA", 742: "TGO", 744: "TUN", 746: "UGA", 748: "BFA", 754: "ZMB",
    # Asia & Pacific
    513: "LKA", 514: "VNM", 516: "BGD", 518: "MMR", 522: "KHM", 524: "LAO",
    532: "HKG", 534: "IND", 536: "IDN", 542: "KOR", 544: "MYS", 548: "MDV",
    556: "NPL", 558: "PAK", 564: "PHL", 565: "PNG", 566: "SGP", 576: "THA",
    578: "TLS", 582: "WSM", 924: "CHN", 928: "TWN",
    # Europe (transition / others)
    911: "RUS", 912: "UKR", 913: "BLR", 914: "ALB", 915: "MDA", 916: "EST",
    917: "LVA", 918: "LTU", 921: "HRV", 922: "SVN", 923: "MKD", 926: "POL",
    935: "CZE", 936: "SVK", 939: "BIH", 941: "GEO", 942: "SRB", 943: "MNE",
    944: "HUN", 946: "ROU", 961: "XKX", 968: "KSV",
}
