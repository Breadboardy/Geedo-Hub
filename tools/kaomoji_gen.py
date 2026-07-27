#!/usr/bin/env python3
"""Generate firmware/kamoji.h - Geedo's kaomoji face pack.

Every glyph is hand-drawn pixel art (14 rows tall, variable width), because
kaomoji need katakana/Greek/box-drawing characters no embedded ASCII font has.
The C renderer emitted here draws into a 1024-byte SSD1306 page buffer - the
exact frame format of the GDA1 animation container (see tools/pack.py) - so
the firmware can display a kaomoji through the same blit path it already uses
for animations.

Also renders every face into assets/kaomoji_preview.png so humans can check
the whole set at a glance. The generator refuses to emit if any face uses a
glyph that has not been drawn.
"""
import os, re, sys, zlib, struct, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
H = 14          # glyph cell height
SPACING = 1     # px between glyphs
SCREEN_W, SCREEN_H = 128, 64
TOP = 25        # y of glyph row on screen

# ----------------------------------------------------------------- glyph art
# '#' = pixel on. All rows of a glyph must be the same width (<= 14).
def G(*rows):
    w = max(len(r) for r in rows)
    rows = [r.ljust(w, '.') for r in rows]
    while len(rows) < H: rows.append('.' * w)
    return rows

GLYPHS = {
 ' ': G('....'),
 '(': G('...##','..#..','.#...','.#...','#....','#....','#....','#....','#....','.#...','.#...','..#..','...##'),
 ')': G('##...','..#..','...#.','...#.','....#','....#','....#','....#','....#','...#.','...#.','..#..','##...'),
 '[': G('####','#...','#...','#...','#...','#...','#...','#...','#...','#...','#...','#...','####'),
 ']': G('####','...#','...#','...#','...#','...#','...#','...#','...#','...#','...#','...#','####'),
 '/': G('.......#','......#.','......#.','.....#..','.....#..','....#...','....#...','...#....','...#....','..#.....','..#.....','.#......','.#......','#.......'),
 '\\': G('#.......','.#......','.#......','..#.....','..#.....','...#....','...#....','....#...','....#...','.....#..','.....#..','......#.','......#.','.......#'),
 '|': G('#','#','#','#','#','#','#','#','#','#','#','#','#'),
 '_': G('','','','','','','','','','','','','########'),
 '-': G('','','','','','','######'),
 '~': G('','','','','','.##....#','#..#..#.','#...##..'),
 '=': G('','','','','.######','','.######'),
 '+': G('','','','...#...','...#...','...#...','#######','...#...','...#...','...#...'),
 '*': G('','','..#..#..','...##...','.######.','...##...','..#..#..'),
 '^': G('','','...#...','..#.#..','.#...#.','#.....#'),
 '<': G('','','.....#','....#.','...#..','..#...','.#....','#.....','.#....','..#...','...#..','....#.','.....#'),
 '>': G('','','#.....','.#....','..#...','...#..','....#.','.....#','....#.','...#..','..#...','.#....','#.....'),
 '.': G('','','','','','','','','','','','.##.','.##.'),
 ',': G('','','','','','','','','','','..##','..##','..#.','.#..'),
 ';': G('','','','..##','..##','','','','','','..##','..##','..#.','.#..'),
 ':': G('','','','.##.','.##.','','','','','','.##.','.##.'),
 "'": G('.##','.##','.#.'),
 '"': G('##.##','##.##','#..#.'),
 '!': G('.##.','.##.','.##.','.##.','.##.','.##.','.##.','.##.','....','....','.##.','.##.'),
 '?': G('.####.','#....#','#....#','.....#','....#.','...#..','..#...','..#...','......','......','..#...','..#...'),
 '#': G('','..#..#..','..#..#..','########','..#..#..','..#..#..','..#..#..','########','..#..#..','..#..#..'),
 '@': G('.#####.','#.....#','#..##.#','#.#..##','#.#..##','#.#.###','#..#.#.','#......','.#####.'),
 'o': G('','','','','.####.','#....#','#....#','#....#','#....#','.####.'),
 'O': G('','','.#####.','#.....#','#.....#','#.....#','#.....#','#.....#','#.....#','.#####.'),
 '0': G('','','.#####.','#.....#','#....##','#...#.#','#..#..#','##....#','#.....#','.#####.'),
 'x': G('','','','','#....#','.#..#.','..##..','..##..','.#..#.','#....#'),
 'X': G('','','#.....#','.#...#.','..#.#..','...#...','...#...','..#.#..','.#...#.','#.....#'),
 'u': G('','','','','#....#','#....#','#....#','#....#','#...##','.###.#'),
 'U': G('','','#.....#','#.....#','#.....#','#.....#','#.....#','#.....#','#.....#','.#####.'),
 'v': G('','','','','#.....#','#.....#','.#...#.','.#...#.','..#.#..','...#...'),
 'V': G('','','#.....#','#.....#','#.....#','.#...#.','.#...#.','..#.#..','..#.#..','...#...'),
 'T': G('','','#######','...#...','...#...','...#...','...#...','...#...','...#...','...#...'),
 'c': G('','','','','.####.','#....#','#.....','#.....','#....#','.####.'),
 'z': G('','','','','######','....#.','...#..','..#...','.#....','######'),
 'Z': G('','','#######','.....#.','....#..','...#...','..#....','.#.....','#......','#######'),
 'W': G('','','#..#..#','#..#..#','#..#..#','#..#..#','#..#..#','#..#..#','#.###.#','.#...#.'),
 'w': G('','','','','#..#..#','#..#..#','#..#..#','#..#..#','#.###.#','.#...#.'),
 'n': G('','','','','#.###.','##...#','#....#','#....#','#....#','#....#'),
 'd': G('','.....#','.....#','.....#','.#####','#....#','#....#','#....#','#....#','.#####'),
 'b': G('','#.....','#.....','#.....','#####.','#....#','#....#','#....#','#....#','#####.'),
 '3': G('','','.####.','#....#','.....#','..###.','.....#','.....#','#....#','.####.'),
 '9': G('','','.####.','#....#','#....#','.#####','.....#','.....#','#....#','.####.'),
 # ------------- special glyphs -------------
 '´': G('...##','..##.','.##..'),
 '`': G('##...','.##..','..##.'),
 '˘': G('#....#','#....#','.####.'),
 '¯': G('######'),
 '¬': G('','','','','','######','.....#','.....#'),
 '⌐': G('','','','','','######','#.....','#.....'),
 '°': G('.##.','#..#','#..#','.##.'),
 '・': G('','','','','','.##.','####','.##.'),
 '•': G('','','','','.###.','#####','#####','.###.'),
 '◕': G('','.#####.','#.....#','#.##..#','##..#.#','##..#.#','#.##..#','#.....#','#######','.#####.'),
 '●': G('','.#####.','#######','#######','#######','#######','#######','#######','#######','.#####.'),
 '○': G('','.#####.','#.....#','#.....#','#.....#','#.....#','#.....#','#.....#','#.....#','.#####.'),
 '⊙': G('','.#####.','#.....#','#.....#','#..#..#','#.###.#','#..#..#','#.....#','#.....#','.#####.'),
 '□': G('','########','#......#','#......#','#......#','#......#','#......#','#......#','#......#','########'),
 '■': G('','########','########','########','########','########','########','########','########','########'),
 '▽': G('','#########','.#.....#.','.#.....#.','..#...#..','..#...#..','...#.#...','...#.#...','....#....'),
 '☆': G('....#....','....#....','...###...','#########','.#######.','..#####..','..#...#..','.#.....#.','#.......#'),
 '★': G('....#....','....#....','...###...','#########','.#######.','..#####..','..#####..','.##...##.','##.....##'),
 '♡': G('','.##..##.','#..##..#','#......#','#......#','.#....#.','..#..#..','...##...','....#...'),
 '♥': G('','.##..##.','########','########','########','.######.','..####..','...##...','....#...'),
 '♪': G('....#...','....##..','....#.#.','....#..#','....#...','....#...','....#...','..###...','.####...','..##....'),
 '⌒': G('','','..####..','.#....#.','#......#'),
 '‿': G('','','','','','','','','','#......#','.#....#.','..####..'),
 'ω': G('','','','','#..##..#','#..##..#','#..##..#','#..##..#','#..##..#','.##..##.'),
 'ε': G('','','','.####','#....','#....','.###.','#....','#....','.####'),
 'Д': G('','','.######.','..#...#.','..#...#.','..#...#.','..#...#.','..#...#.','.#....#.','########','#......#','#......#'),
 'Σ': G('','#######','.#.....','..#....','...#...','....#..','...#...','..#....','.#.....','#######'),
 'ツ': G('','#.#....#','.#.#...#','...#..#.','......#.','.....#..','.....#..','....#...','...#....','.##.....'),
 'ヮ': G('','','########','.......#','.......#','.......#','......#.','.....#..','....#...','..##....'),
 'ノ': G('','.......#','.......#','......#.','......#.','.....#..','....#...','...#....','..#.....','##......'),
 'ヽ': G('','#.......','.#......','..#.....','..#.....','...#....','....#...','.....#..','......#.','.......#'),
 'っ': G('','','','','.#####.','......#','......#','......#','.....#.','..###..'),
 'つ': G('','','.######.','.......#','.......#','.......#','.......#','......#.','.....#..','..###...'),
 '⊂': G('','','..#####','.#.....','#......','#......','#......','#......','.#.....','..#####'),
 '⊃': G('','','#####..','.....#.','......#','......#','......#','......#','.....#.','#####..'),
 '─': G('','','','','','','########'),
 '━': G('','','','','','','########','########'),
 '┻': G('','','...##...','...##...','...##...','...##...','...##...','########','########'),
 '┬': G('','','','','','','########','...#....','...#....','...#....','...#....','...#....','...#....','...#....'),
 '╯': G('','...#....','...#....','...#....','...#....','...#....','...#....','####....'),
 '︵': G('','','','','','..####..','.#....#.','#......#'),
 '益': G('#..##..#','.#.##.#.','########','........','.#.#.#..','.#.#.#.#','########','#..#..#.','#..#..#.','########'),
 '←': G('','','','...#....','..#.....','.#......','########','.#......','..#.....','...#....'),
 '→': G('','','','....#...','.....#..','......#.','########','......#.','.....#..','....#...'),
 '≧': G('','#....','.##..','...##','.##..','#....','.....','#####','.....','#####'),
 '≦': G('','....#','..##.','##...','..##.','....#','.....','#####','.....','#####'),
 'ʕ': G('..###','.#...','#....','#....','#....','#....','#....','#....','#....','#....','.#...','..###'),
 'ʔ': G('###..','...#.','....#','....#','....#','....#','....#','....#','....#','....#','...#.','###..'),
 'ʖ': G('','','','','.#....','.#....','.#....','.#..#.','#..#.#','#..#.#','.##.##'),
 'ᴥ': G('','','','','#.....#','##...##','#.###.#','#.....#','.#...#.','..###..'),
 '͜': G('','','','','','','','','','','#....#','.####.'),
 '͡°': G('.####.','#....#','..##..','..##..','..##..'),
 'ಠ': G('.#####.','#.....#','#.###.#','#.#.#.#','#.###.#','#.....#','.#####.','...#...','..#....','.#####.'),
 'ಥ': G('.#####.','#.....#','#.###.#','#.#.#.#','#.#.#.#','#.##..#','#....##','.#####.','...#...','.#####.'),
 '人': G('','','....#....','....#....','...#.#...','...#.#...','..#...#..','..#...#..','.#.....#.','.#.....#.','#.......#'),
 '彡': G('','....###','..##...','.#..###','...#...','..#..##','....#..','...#...','..#....','.#.....'),
}

# ----------------------------------------------------------------- the faces
# (id, category, face). Only characters drawn above may appear.
FACES = [
 # --- happy
 ('happy_classic',      'happy', '(^_^)'),
 ('happy_dash',         'happy', '(^-^)'),
 ('happy_open',         'happy', '(^o^)'),
 ('happy_dot',          'happy', '(^.^)'),
 ('happy_vee',          'happy', '(^v^)'),
 ('happy_cheer',        'happy', '\\(^o^)/'),
 ('happy_nn',           'happy', '(n_n)'),
 ('happy_peace',        'happy', '(^_^)v'),
 ('happy_thumbs',       'happy', 'd(^_^)b'),
 ('happy_blush',        'happy', '(*^_^*)'),
 ('happy_wink',         'happy', '(^_~)'),
 ('happy_wink2',        'happy', '(~_^)'),
 ('happy_glee',         'happy', '(≧▽≦)'),
 ('happy_glee_cheer',   'happy', '\\(≧▽≦)/'),
 ('happy_gleeful',      'happy', '(≧ω≦)'),
 ('happy_soft',         'happy', '(´▽`)'),
 ('happy_gentle',       'happy', '(´ω`)'),
 ('happy_round',        'happy', '(o´▽`o)'),
 ('happy_dance',        'happy', 'ヽ(´▽`)ノ'),
 ('happy_yay',          'happy', 'ヽ(^o^)ノ'),
 ('happy_starstruck',   'happy', '(☆▽☆)'),
 ('happy_starry',       'happy', '(★ω★)'),
 ('happy_curve',        'happy', '(⌒‿⌒)'),
 ('happy_uwu',          'happy', '(◕‿◕)'),
 ('happy_dots',         'happy', "('‿')"),
 ('happy_oo',           'happy', '(o‿o)'),
 ('happy_smilearc',     'happy', '(^‿^)'),
 ('happy_cheeky',       'happy', '(^3^)'),
 ('happy_note',         'happy', '♪(´▽`)'),
 ('happy_bright',       'happy', '(●‿●)'),
 # --- love
 ('love_hearteyes',     'love', '(♡_♡)'),
 ('love_hearteyes2',    'love', '(♥_♥)'),
 ('love_soft',          'love', '(♡ω♡)'),
 ('love_glow',          'love', '(♡´▽`♡)'),
 ('love_hug_heart',     'love', '♡(◕‿◕)♡'),
 ('love_kiss',          'love', '(´ε`)♡'),
 ('love_kiss2',         'love', '(˘3˘)♡'),
 ('love_kiss3',         'love', '(-ε-)♡'),
 ('love_sparkle',       'love', '(*♡▽♡*)'),
 ('love_whistle',       'love', '♪~(´ε`)'),
 # --- sad / cry
 ('cry_classic',        'sad', '(T_T)'),
 ('cry_flood',          'sad', '(T▽T)'),
 ('cry_semis',          'sad', '(;_;)'),
 ('cry_soft',           'sad', '(;ω;)'),
 ('cry_stream',         'sad', '(´;ω;`)'),
 ('cry_hard',           'sad', '(T^T)'),
 ('cry_oh',             'sad', '(ToT)'),
 ('cry_wobble',         'sad', '(TωT)'),
 ('cry_pillar',         'sad', '(┬_┬)'),
 ('cry_stare',          'sad', '(ಥ_ಥ)'),
 ('sad_blank',          'sad', '(._.)'),
 ('sad_droop',          'sad', '(,_,)'),
 ('sad_quiet',          'sad', '(´_`)'),
 ('sad_down',           'sad', '(u_u)'),
 ('sad_sigh',           'sad', '(=_=)'),
 ('sad_hurt',           'sad', '(>_<)'),
 ('sad_worry',          'sad', '(°~°)'),
 ('sad_sweat',          'sad', '(^_^;)'),
 ('sad_nervous',        'sad', '(._.;)'),
 ('sad_strain',         'sad', '(´~`)'),
 ('sad_wince',          'sad', '(>~<)'),
 # --- angry
 ('angry_look',         'angry', '(ಠ_ಠ)'),
 ('angry_rage_look',    'angry', '(ಠ益ಠ)'),
 ('angry_side',         'angry', '(¬_¬)'),
 ('angry_growl',        'angry', '(`Д´)'),
 ('angry_vein',         'angry', '(#`Д´)'),
 ('angry_grr',          'angry', '(`ω´)'),
 ('angry_plain',        'angry', '(`_´)'),
 ('angry_boil',         'angry', '(°益°)'),
 ('angry_charge',       'angry', '(ノ`Д´)ノ'),
 ('angry_tableflip',    'angry', '(╯°□°)╯︵ ┻━┻'),
 ('angry_tableback',    'angry', '┬─┬ノ(°_°ノ)'),
 ('angry_glare',        'angry', '(•`_´•)'),
 # --- surprised
 ('surp_big',           'surprised', '(O_O)'),
 ('surp_small',         'surprised', '(o_o)'),
 ('surp_zero',          'surprised', '(0_0)'),
 ('surp_dot',           'surprised', '(O.O)'),
 ('surp_deg',           'surprised', '(°o°)'),
 ('surp_deg2',          'surprised', '(°O°)'),
 ('surp_shock',         'surprised', '(°□°)'),
 ('surp_wow',           'surprised', 'w(°o°)w'),
 ('surp_jump',          'surprised', 'Σ(°□°)'),
 ('surp_jolt',          'surprised', 'Σ(O_O)'),
 ('surp_dizzy',         'surprised', '(@_@)'),
 ('surp_target',        'surprised', '(⊙_⊙)'),
 # --- confused
 ('conf_what',          'confused', '(?_?)'),
 ('conf_skew',          'confused', '(o_O)'),
 ('conf_skew2',         'confused', '(O_o)'),
 ('conf_dot',           'confused', '(・_・)'),
 ('conf_soft',          'confused', '(・ω・)'),
 ('conf_shifty_r',      'confused', '(→_→)'),
 ('conf_shifty_l',      'confused', '(←_←)'),
 ('conf_hmm',           'confused', '(~_~)'),
 # --- sleepy
 ('sleep_flat',         'sleepy', '(-_-)'),
 ('sleep_heavy',        'sleepy', '(=_=)zzz'),
 ('sleep_dot',          'sleepy', '(-.-)'),
 ('sleep_soft',         'sleepy', '(-ω-)'),
 ('sleep_cozy',         'sleepy', '(˘ω˘)'),
 ('sleep_zz',           'sleepy', '(-_-)zzz'),
 ('sleep_calm',         'sleepy', '(=ω=)'),
 # --- cool / smug
 ('cool_lenny',         'cool', '( ͡° ͜ʖ ͡°)'),
 ('cool_smug',          'cool', '(¬‿¬)'),
 ('cool_shades',        'cool', '(■_■)'),
 ('cool_dealwith',      'cool', '(⌐■_■)'),
 ('cool_robot',         'cool', '[■_■]'),
 # --- actions
 ('act_shrug',          'action', '¯\\_(ツ)_/¯'),
 ('act_shrug_dance',    'action', 'ヽ(ツ)ノ'),
 ('act_hug',            'action', '(っ´▽`)っ'),
 ('act_hug_big',        'action', '(⊃´▽`)⊃'),
 ('act_hug_want',       'action', '(つ°ω°)つ'),
 ('act_celebrate',      'action', '(ノ´▽`)ノ'),
 ('act_panic',          'action', 'ヽ(°□°)ノ'),
 ('act_run',            'action', 'ε=ε=(ノ≧▽≦)ノ'),
 ('act_fight',          'action', '(o°ω°)o'),
 ('act_wave',           'action', '(^_^)/'),
 ('act_wave_soft',      'action', '(´▽`)/'),
 ('act_hello',          'action', 'ヽ(^_^)'),
 ('act_magic',          'action', '(ノ◕ヮ◕)ノ*:・'),
 ('act_party',          'action', 'ヽ(^▽^)ノ'),
 ('act_star',           'action', '☆彡'),
 # --- animals
 ('bear',               'animal', 'ʕ•ᴥ•ʔ'),
 ('bear_happy',         'animal', 'ʕ´•ᴥ•`ʔ'),
 ('cat',                'animal', '(=^・^=)'),
 ('cat_soft',           'animal', '(=^ω^=)'),
 ('cat_grump',          'animal', '(=`ω´=)'),
 ('dog',                'animal', '(U・ᴥ・U)'),
 ('fish',               'animal', '<°))))><'),
 # --- robot geedo
 ('robot_neutral',      'robot', '[o_o]'),
 ('robot_happy',        'robot', '[^_^]'),
 ('robot_deg',          'robot', '[°_°]'),
 ('robot_sleep',        'robot', '[-_-]'),
 ('robot_love',         'robot', '[♡_♡]'),
 ('robot_shock',        'robot', '[°□°]'),
 # --- dead / broken
 ('dead_x',             'dead', '(x_x)'),
 ('dead_XX',            'dead', '(X_X)'),
 ('dead_plus',          'dead', '(+_+)'),
 # --- more happy
 ('happy_grin',         'happy', '(≧∀≦)'.replace('∀','▽')),
 ('happy_beam',         'happy', '(O▽O)'),
 ('happy_squee',        'happy', '(>▽<)'),
 ('happy_tearsjoy',     'happy', '(;▽;)'),
 ('happy_flower',       'happy', '(´‿`)'),
 ('happy_ooo',          'happy', '(o‿O)'),
 ('happy_hooray',       'happy', '\\(´▽`)/'),
 ('happy_bounce',       'happy', 'ヽ(≧ω≦)ノ'),
 ('happy_twinkle',      'happy', '(☆‿☆)'),
 ('happy_proud',        'happy', '(^▽^)'),
 ('happy_wide',         'happy', '(⌒▽⌒)'),
 ('happy_warm',         'happy', '(˘‿˘)'),
 # --- more love
 ('love_shy',           'love', "(/♡_♡)/"),
 ('love_beam',          'love', '(♥‿♥)'),
 ('love_throw',         'love', '(ノ♡▽♡)ノ'),
 ('love_daydream',      'love', '(´♡‿♡`)'),
 ('love_cat',           'love', '(=♡ω♡=)'),
 # --- more sad
 ('sad_gloom',          'sad', '(´-_-`)'),
 ('sad_rain',           'sad', '(;O;)'),
 ('sad_please',         'sad', '(;人;)'),
 ('sad_tired',          'sad', '(=Д=)'),
 ('sad_defeat',         'sad', '(´Д`)'),
 # --- more angry
 ('angry_fume',         'angry', '(¬益¬)'),
 ('angry_snap',         'angry', '(>Д<)'),
 ('angry_scheme',       'angry', '(`◕‿◕´)'),
 # --- more surprised / confused
 ('surp_gasp',          'surprised', '(⊙Д⊙)'),
 ('surp_blink',         'surprised', '(●_●)'),
 ('surp_frozen',        'surprised', '(:O_O:)'.replace(':','')),
 ('conf_swirl',         'confused', '(@ω@)'),
 ('conf_broken',        'confused', '(°ω°;)'),
 ('conf_tilt',          'confused', '(・_・?)'),
 # --- more actions
 ('act_pray',           'action', '(-人-)'),
 ('act_please',         'action', '(´人`)'),
 ('act_throw_star',     'action', '(ノ°▽°)ノ☆彡'),
 ('act_catch',          'action', '(⊃°▽°)⊃'),
 ('act_march',          'action', 'ε=(ノ・ω・)ノ'),
 ('act_tada',           'action', '\\(☆▽☆)/'),
 ('act_comfort',        'action', '(っ´ω`)っ'),
 ('act_highfive',       'action', '(^_^)人(^_^)'),
 ('act_cheer_pair',     'action', 'ヽ(´▽`)人(´▽`)ノ'.replace('人(´▽`)ノ','ノ')),
 ('act_salute',         'action', '(^_^)ゞ'.replace('ゞ','/')),
 # --- more animals
 ('bear_wave',          'animal', 'ʕ•ᴥ•ʔノ'),
 ('bear_love',          'animal', 'ʕ♡ᴥ♡ʔ'),
 ('cat_sleep',          'animal', '(=-ω-=)'),
 ('cat_alert',          'animal', '(=°ω°=)'),
 ('dog_happy',          'animal', '(U^ᴥ^U)'),
 ('bird_look',          'animal', '(・◕・)'),
 # --- more robot geedo
 ('robot_wink',         'robot', '[^_~]'),
 ('robot_glee',         'robot', '[≧▽≦]'),
 ('robot_hmm',          'robot', '[¬_¬]'),
 ('robot_uwu',          'robot', '[◕‿◕]'),
 ('robot_dead',         'robot', '[x_x]'),
 ('robot_star',         'robot', '[☆_☆]'),
 ('robot_wave',         'robot', '[o_o]/'),
 ('robot_zen',          'robot', '[-人-]'),
]

# ------------------------------------------------------------------ renderer
def tokenize(face):
    keys = sorted(GLYPHS.keys(), key=len, reverse=True)
    out, i = [], 0
    while i < len(face):
        for k in keys:
            if face.startswith(k, i):
                out.append(k); i += len(k); break
        else:
            raise KeyError(f"no glyph for {face[i]!r} (U+{ord(face[i]):04X}) in face {face!r}")
    return out

def render(face):
    toks = tokenize(face)
    widths = [len(GLYPHS[t][0]) for t in toks]
    total = sum(widths) + SPACING * (len(toks) - 1)
    assert total <= SCREEN_W, f"{face!r} is {total}px wide (max {SCREEN_W})"
    fb = [[0]*SCREEN_W for _ in range(SCREEN_H)]
    x = (SCREEN_W - total) // 2
    for t, w in zip(toks, widths):
        for ry, row in enumerate(GLYPHS[t]):
            for rx, c in enumerate(row):
                if c == '#': fb[TOP + ry][x + rx] = 1
        x += w + SPACING
    return fb

# ------------------------------------------------------------------ verify
bad = []
for _id, cat, face in FACES:
    try: render(face)
    except (KeyError, AssertionError) as e: bad.append(str(e))
if bad:
    print("GENERATION BLOCKED:")
    for b in sorted(set(bad)): print("  ", b)
    sys.exit(1)
print(f"{len(FACES)} faces, {len(GLYPHS)} glyphs, all renderable")

# ------------------------------------------------------------------ preview
def write_png(path, rgb, w, h):
    raw = b''.join(b'\x00' + bytes(v for px in row for v in px) for row in rgb)
    def ch(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n'
           + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
           + ch(b'IDAT', zlib.compress(raw, 9)) + ch(b'IEND', b''))
    open(path, 'wb').write(png)

COLS = 6
CW, CH = SCREEN_W + 4, 26
rows = (len(FACES) + COLS - 1) // COLS
img = [[(12, 22, 46)] * (COLS * CW) for _ in range(rows * CH)]
for idx, (_id, cat, face) in enumerate(FACES):
    fb = render(face)
    ox, oy = (idx % COLS) * CW + 2, (idx // COLS) * CH + 4
    for y in range(TOP, TOP + H + 2):
        for x in range(SCREEN_W):
            if y < SCREEN_H and fb[y][x]:
                img[oy + y - TOP][ox + x] = (255, 255, 255)
write_png(ROOT / 'assets' / 'kaomoji_preview.png',
          img, COLS * CW, rows * CH)
print("wrote assets/kaomoji_preview.png")

# ------------------------------------------------------------------ emit .h
def cbytes(s):
    return ''.join(f'\\x{b:02x}' for b in s.encode('utf-8'))

glyph_ids = {k: i for i, k in enumerate(GLYPHS)}
lines = []
lines.append('// kamoji.h - Geedo kaomoji face pack (auto-generated by tools/kaomoji_gen.py)')
lines.append('// Do not hand-edit; add faces/glyphs in the generator and re-run.')
lines.append('//')
lines.append('// kaomoji_render() draws into a 1024-byte SSD1306 page buffer - the same')
lines.append('// frame format as the GDA1 animation container - so the result can go')
lines.append('// through the exact display path the animation player already uses.')
lines.append('#pragma once')
lines.append('#include <stdint.h>')
lines.append('#include <string.h>')
lines.append('#if defined(ARDUINO)')
lines.append('#include <pgmspace.h>')
lines.append('#else')
lines.append('#define PROGMEM')
lines.append('#define pgm_read_byte(p)  (*(const uint8_t*)(p))')
lines.append('#define pgm_read_word(p)  (*(const uint16_t*)(p))')
lines.append('#define pgm_read_ptr(p)   (*(const void* const*)(p))')
lines.append('#endif')
lines.append('')
lines.append(f'#define KAOMOJI_COUNT {len(FACES)}')
lines.append(f'#define KAOMOJI_GLYPHS {len(GLYPHS)}')
lines.append(f'#define KAOMOJI_CELL_H {H}')
lines.append(f'#define KAOMOJI_TOP {TOP}')
lines.append('')
# glyph bitmaps: width byte + H x uint16 (row bits, MSB = leftmost)
lines.append('// each glyph: [width][14 x uint16 row bitmaps, MSB-first]')
for k, i in glyph_ids.items():
    rows_ = GLYPHS[k]
    w = len(rows_[0])
    words = []
    for r in rows_:
        v = 0
        for x, c in enumerate(r):
            if c == '#': v |= 1 << (15 - x)
        words.append(v)
    ws = ','.join(f'0x{v:04x}' for v in words)
    lines.append(f'static const uint16_t KG_{i}[{H}] PROGMEM = {{{ws}}}; // {k!r} w={w}')
lines.append(f'static const uint16_t* const KAOMOJI_GLYPH_ROWS[{len(GLYPHS)}] PROGMEM = {{'
             + ','.join(f'KG_{i}' for i in glyph_ids.values()) + '};')
lines.append('static const uint8_t KAOMOJI_GLYPH_W[] PROGMEM = {'
             + ','.join(str(len(GLYPHS[k][0])) for k in glyph_ids) + '};')
# utf8 keys, longest first for the tokenizer
key_order = sorted(GLYPHS, key=lambda k: len(k.encode('utf-8')), reverse=True)
lines.append('static const char KAOMOJI_GLYPH_UTF8[] PROGMEM = "'
             + ''.join(cbytes(k) + '\\x00' for k in key_order) + '";')
lines.append('static const uint8_t KAOMOJI_GLYPH_KEYIDX[] PROGMEM = {'
             + ','.join(str(glyph_ids[k]) for k in key_order) + '};')
lines.append('')
# faces
for i, (_id, cat, face) in enumerate(FACES):
    lines.append(f'static const char KF_{i}[] PROGMEM = "{cbytes(face)}"; // {_id}: {face}')
lines.append(f'static const char* const KAOMOJI_FACES[{len(FACES)}] PROGMEM = {{'
             + ','.join(f'KF_{i}' for i in range(len(FACES))) + '};')
cats = sorted({c for _, c, _ in FACES})
cat_id = {c: i for i, c in enumerate(cats)}
lines.append('static const char* const KAOMOJI_CATEGORY_NAMES[] PROGMEM = {'
             + ','.join(f'"{c}"' for c in cats) + '};')
lines.append(f'#define KAOMOJI_CATEGORY_COUNT {len(cats)}')
lines.append('static const uint8_t KAOMOJI_FACE_CATEGORY[] PROGMEM = {'
             + ','.join(str(cat_id[c]) for _, c, _ in FACES) + '};')
lines.append('')
lines.append(r'''
// ---- tokenizer: longest-match against the glyph table -----------------
static inline int kaomoji_match_(const char* s, uint8_t* gid) {
  const char* p = KAOMOJI_GLYPH_UTF8;
  for (uint16_t k = 0; k < KAOMOJI_GLYPHS; k++) {
    uint8_t n = 0;
    while (pgm_read_byte(p + n)) n++;
    uint8_t ok = 1;
    for (uint8_t j = 0; j < n; j++)
      if ((uint8_t)s[j] != pgm_read_byte(p + j)) { ok = 0; break; }
    if (ok && n) { *gid = pgm_read_byte(&KAOMOJI_GLYPH_KEYIDX[k]); return n; }
    p += n + 1;
  }
  return 0;   // unknown byte - caller skips one byte
}

// pixel width of a face when rendered (0 if any glyph is unknown)
static inline int kaomoji_width(const char* face) {
  int w = 0, first = 1;
  while (*face) {
    uint8_t gid; int n = kaomoji_match_(face, &gid);
    if (!n) { face++; continue; }
    if (!first) w += 1;
    w += pgm_read_byte(&KAOMOJI_GLYPH_W[gid]);
    first = 0; face += n;
  }
  return w;
}

// Render a face centred into a 1024-byte SSD1306 page buffer (128x64,
// 8 pages, LSB = top row of page) - identical to a GDA1 animation frame.
// Clears the buffer first. Returns rendered width in px.
static inline int kaomoji_render(const char* face, uint8_t* frame1024) {
  memset(frame1024, 0, 1024);
  int total = kaomoji_width(face);
  int x = (128 - total) / 2;
  if (x < 0) x = 0;
  while (*face) {
    uint8_t gid; int n = kaomoji_match_(face, &gid);
    if (!n) { face++; continue; }
    const uint16_t* rows = (const uint16_t*)pgm_read_ptr(&KAOMOJI_GLYPH_ROWS[gid]);
    uint8_t gw = pgm_read_byte(&KAOMOJI_GLYPH_W[gid]);
    for (uint8_t ry = 0; ry < KAOMOJI_CELL_H; ry++) {
      uint16_t bits = pgm_read_word(&rows[ry]);
      uint8_t y = KAOMOJI_TOP + ry;
      for (uint8_t rx = 0; rx < gw; rx++) {
        if (bits & (0x8000 >> rx)) {
          int px = x + rx;
          if (px >= 0 && px < 128)
            frame1024[(y >> 3) * 128 + px] |= (1 << (y & 7));
        }
      }
    }
    x += gw + 1; face += n;
  }
  return total;
}

// convenience accessors (face strings live in PROGMEM)
static inline const char* kaomoji_face(uint16_t i) {
  return (const char*)pgm_read_ptr(&KAOMOJI_FACES[i]);
}
static inline uint8_t kaomoji_category(uint16_t i) {
  return pgm_read_byte(&KAOMOJI_FACE_CATEGORY[i]);
}
// render face #i straight into a frame buffer
static inline int kaomoji_show(uint16_t i, uint8_t* frame1024) {
  char buf[48];
  const char* f = kaomoji_face(i % KAOMOJI_COUNT);
  uint8_t j = 0;
  while (j < sizeof(buf) - 1 && (buf[j] = pgm_read_byte(f + j))) j++;
  buf[j] = 0;
  return kaomoji_render(buf, frame1024);
}
''')
out = '\n'.join(lines) + '\n'
(ROOT / 'firmware').mkdir(exist_ok=True)
(ROOT / 'firmware' / 'kamoji.h').write_text(out)
print(f"wrote firmware/kamoji.h ({len(out)//1024} KB, {len(FACES)} faces, {len(GLYPHS)} glyphs)")
