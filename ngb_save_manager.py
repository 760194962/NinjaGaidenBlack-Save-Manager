#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ngb_save_manager.py - Ninja Gaiden Black (Xbox, title 5443000D) save manager (GUI)

Usage:  python ngb_save_manager.py [path to ...\\5443000d]
        python ngb_save_manager.py --selftest <path to ...\\5443000d>

Shows slot, chapter / mission, play time, difficulty per save; moves slots, re-signs saves and
system.dat for another HD key, and edits system.dat (play-time table / list order).
No key is needed to READ saves (decryption only needs the seed stored in the file).
"""
import os, re, struct, sys, csv, json
from ngb_i18n import t, set_lang

MOD = 2**48 - 59                       # XDK folder-name hash modulus (prime)
SAVE_SIZE = 0x174A8                    # save000.dat size
SYSTEM_SIZE = 0x550                    # TDATA\5443000d\system.dat size (same signature scheme)
DATA_OFF = 0x18                        # header: 0x14 HMAC sig + 0x04 seed
TAIL = bytes([0x94, 0x45, 0x8E, 0xD2, 0x8A, 0x4F])
# offsets inside the DECRYPTED data (i.e. file offset - 0x18)
OFF_PLAYTIME = 0x16653   # u32, 60 frames per second
OFF_KARMA = 0x1664B      # u32 (matches the in-game KARMA on a Mission save; unaligned)
OFF_DIFFICULTY = 0x16840 # u8 (0..4)  -- inferred, see notes
OFF_CHAPTER0 = 0x16842   # u8, 0-based chapter index
OFF_SAVEPOINT = 0x16849  # u8, looks like a save-point/area id that changes within a chapter (meaning NOT decoded yet)
DIFFICULTY = {0: "Ninja Dog", 1: "Normal", 2: "Hard", 3: "Very Hard", 4: "Master Ninja"}

def folder_id(name):
    """Folder name = 12 hex digits of h, h = (h*0x10000 + utf16_unit) mod (2^48-59), over the save name."""
    h = 0
    for u in [ord(c) for c in name]:
        h = (h * 0x10000 + u) % MOD
    return "%012X" % h

# ---------------- Blowfish / Mersenne-Twister (ported from feudalnate/NinjaCrypt) ----------------
M32 = 0xFFFFFFFF
P0 = [
    0x243F6A88, 0x85A308D3, 0x13198A2E, 0x03707344, 0xA4093822, 0x299F31D0, 0x082EFA98, 0xEC4E6C89,
    0x452821E6, 0x38D01377, 0xBE5466CF, 0x34E90C6C, 0xC0AC29B7, 0xC97C50DD, 0x3F84D5B5, 0xB5470917,
    0x9216D5D9, 0x8979FB1B
]
S0 = [
    [
    0xD1310BA6, 0x98DFB5AC, 0x2FFD72DB, 0xD01ADFB7, 0xB8E1AFED, 0x6A267E96, 0xBA7C9045, 0xF12C7F99,
    0x24A19947, 0xB3916CF7, 0x0801F2E2, 0x858EFC16, 0x636920D8, 0x71574E69, 0xA458FEA3, 0xF4933D7E,
    0x0D95748F, 0x728EB658, 0x718BCD58, 0x82154AEE, 0x7B54A41D, 0xC25A59B5, 0x9C30D539, 0x2AF26013,
    0xC5D1B023, 0x286085F0, 0xCA417918, 0xB8DB38EF, 0x8E79DCB0, 0x603A180E, 0x6C9E0E8B, 0xB01E8A3E,
    0xD71577C1, 0xBD314B27, 0x78AF2FDA, 0x55605C60, 0xE65525F3, 0xAA55AB94, 0x57489862, 0x63E81440,
    0x55CA396A, 0x2AAB10B6, 0xB4CC5C34, 0x1141E8CE, 0xA15486AF, 0x7C72E993, 0xB3EE1411, 0x636FBC2A,
    0x2BA9C55D, 0x741831F6, 0xCE5C3E16, 0x9B87931E, 0xAFD6BA33, 0x6C24CF5C, 0x7A325381, 0x28958677,
    0x3B8F4898, 0x6B4BB9AF, 0xC4BFE81B, 0x66282193, 0x61D809CC, 0xFB21A991, 0x487CAC60, 0x5DEC8032,
    0xEF845D5D, 0xE98575B1, 0xDC262302, 0xEB651B88, 0x23893E81, 0xD396ACC5, 0x0F6D6FF3, 0x83F44239,
    0x2E0B4482, 0xA4842004, 0x69C8F04A, 0x9E1F9B5E, 0x21C66842, 0xF6E96C9A, 0x670C9C61, 0xABD388F0,
    0x6A51A0D2, 0xD8542F68, 0x960FA728, 0xAB5133A3, 0x6EEF0B6C, 0x137A3BE4, 0xBA3BF050, 0x7EFB2A98,
    0xA1F1651D, 0x39AF0176, 0x66CA593E, 0x82430E88, 0x8CEE8619, 0x456F9FB4, 0x7D84A5C3, 0x3B8B5EBE,
    0xE06F75D8, 0x85C12073, 0x401A449F, 0x56C16AA6, 0x4ED3AA62, 0x363F7706, 0x1BFEDF72, 0x429B023D,
    0x37D0D724, 0xD00A1248, 0xDB0FEAD3, 0x49F1C09B, 0x075372C9, 0x80991B7B, 0x25D479D8, 0xF6E8DEF7,
    0xE3FE501A, 0xB6794C3B, 0x976CE0BD, 0x04C006BA, 0xC1A94FB6, 0x409F60C4, 0x5E5C9EC2, 0x196A2463,
    0x68FB6FAF, 0x3E6C53B5, 0x1339B2EB, 0x3B52EC6F, 0x6DFC511F, 0x9B30952C, 0xCC814544, 0xAF5EBD09,
    0xBEE3D004, 0xDE334AFD, 0x660F2807, 0x192E4BB3, 0xC0CBA857, 0x45C8740F, 0xD20B5F39, 0xB9D3FBDB,
    0x5579C0BD, 0x1A60320A, 0xD6A100C6, 0x402C7279, 0x679F25FE, 0xFB1FA3CC, 0x8EA5E9F8, 0xDB3222F8,
    0x3C7516DF, 0xFD616B15, 0x2F501EC8, 0xAD0552AB, 0x323DB5FA, 0xFD238760, 0x53317B48, 0x3E00DF82,
    0x9E5C57BB, 0xCA6F8CA0, 0x1A87562E, 0xDF1769DB, 0xD542A8F6, 0x287EFFC3, 0xAC6732C6, 0x8C4F5573,
    0x695B27B0, 0xBBCA58C8, 0xE1FFA35D, 0xB8F011A0, 0x10FA3D98, 0xFD2183B8, 0x4AFCB56C, 0x2DD1D35B,
    0x9A53E479, 0xB6F84565, 0xD28E49BC, 0x4BFB9790, 0xE1DDF2DA, 0xA4CB7E33, 0x62FB1341, 0xCEE4C6E8,
    0xEF20CADA, 0x36774C01, 0xD07E9EFE, 0x2BF11FB4, 0x95DBDA4D, 0xAE909198, 0xEAAD8E71, 0x6B93D5A0,
    0xD08ED1D0, 0xAFC725E0, 0x8E3C5B2F, 0x8E7594B7, 0x8FF6E2FB, 0xF2122B64, 0x8888B812, 0x900DF01C,
    0x4FAD5EA0, 0x688FC31C, 0xD1CFF191, 0xB3A8C1AD, 0x2F2F2218, 0xBE0E1777, 0xEA752DFE, 0x8B021FA1,
    0xE5A0CC0F, 0xB56F74E8, 0x18ACF3D6, 0xCE89E299, 0xB4A84FE0, 0xFD13E0B7, 0x7CC43B81, 0xD2ADA8D9,
    0x165FA266, 0x80957705, 0x93CC7314, 0x211A1477, 0xE6AD2065, 0x77B5FA86, 0xC75442F5, 0xFB9D35CF,
    0xEBCDAF0C, 0x7B3E89A0, 0xD6411BD3, 0xAE1E7E49, 0x00250E2D, 0x2071B35E, 0x226800BB, 0x57B8E0AF,
    0x2464369B, 0xF009B91E, 0x5563911D, 0x59DFA6AA, 0x78C14389, 0xD95A537F, 0x207D5BA2, 0x02E5B9C5,
    0x83260376, 0x6295CFA9, 0x11C81968, 0x4E734A41, 0xB3472DCA, 0x7B14A94A, 0x1B510052, 0x9A532915,
    0xD60F573F, 0xBC9BC6E4, 0x2B60A476, 0x81E67400, 0x08BA6FB5, 0x571BE91F, 0xF296EC6B, 0x2A0DD915,
    0xB6636521, 0xE7B9F9B6, 0xFF34052E, 0xC5855664, 0x53B02D5D, 0xA99F8FA1, 0x08BA4799, 0x6E85076A
    ],
    [
    0x4B7A70E9, 0xB5B32944, 0xDB75092E, 0xC4192623, 0xAD6EA6B0, 0x49A7DF7D, 0x9CEE60B8, 0x8FEDB266,
    0xECAA8C71, 0x699A17FF, 0x5664526C, 0xC2B19EE1, 0x193602A5, 0x75094C29, 0xA0591340, 0xE4183A3E,
    0x3F54989A, 0x5B429D65, 0x6B8FE4D6, 0x99F73FD6, 0xA1D29C07, 0xEFE830F5, 0x4D2D38E6, 0xF0255DC1,
    0x4CDD2086, 0x8470EB26, 0x6382E9C6, 0x021ECC5E, 0x09686B3F, 0x3EBAEFC9, 0x3C971814, 0x6B6A70A1,
    0x687F3584, 0x52A0E286, 0xB79C5305, 0xAA500737, 0x3E07841C, 0x7FDEAE5C, 0x8E7D44EC, 0x5716F2B8,
    0xB03ADA37, 0xF0500C0D, 0xF01C1F04, 0x0200B3FF, 0xAE0CF51A, 0x3CB574B2, 0x25837A58, 0xDC0921BD,
    0xD19113F9, 0x7CA92FF6, 0x94324773, 0x22F54701, 0x3AE5E581, 0x37C2DADC, 0xC8B57634, 0x9AF3DDA7,
    0xA9446146, 0x0FD0030E, 0xECC8C73E, 0xA4751E41, 0xE238CD99, 0x3BEA0E2F, 0x3280BBA1, 0x183EB331,
    0x4E548B38, 0x4F6DB908, 0x6F420D03, 0xF60A04BF, 0x2CB81290, 0x24977C79, 0x5679B072, 0xBCAF89AF,
    0xDE9A771F, 0xD9930810, 0xB38BAE12, 0xDCCF3F2E, 0x5512721F, 0x2E6B7124, 0x501ADDE6, 0x9F84CD87,
    0x7A584718, 0x7408DA17, 0xBC9F9ABC, 0xE94B7D8C, 0xEC7AEC3A, 0xDB851DFA, 0x63094366, 0xC464C3D2,
    0xEF1C1847, 0x3215D908, 0xDD433B37, 0x24C2BA16, 0x12A14D43, 0x2A65C451, 0x50940002, 0x133AE4DD,
    0x71DFF89E, 0x10314E55, 0x81AC77D6, 0x5F11199B, 0x043556F1, 0xD7A3C76B, 0x3C11183B, 0x5924A509,
    0xF28FE6ED, 0x97F1FBFA, 0x9EBABF2C, 0x1E153C6E, 0x86E34570, 0xEAE96FB1, 0x860E5E0A, 0x5A3E2AB3,
    0x771FE71C, 0x4E3D06FA, 0x2965DCB9, 0x99E71D0F, 0x803E89D6, 0x5266C825, 0x2E4CC978, 0x9C10B36A,
    0xC6150EBA, 0x94E2EA78, 0xA5FC3C53, 0x1E0A2DF4, 0xF2F74EA7, 0x361D2B3D, 0x1939260F, 0x19C27960,
    0x5223A708, 0xF71312B6, 0xEBADFE6E, 0xEAC31F66, 0xE3BC4595, 0xA67BC883, 0xB17F37D1, 0x018CFF28,
    0xC332DDEF, 0xBE6C5AA5, 0x65582185, 0x68AB9802, 0xEECEA50F, 0xDB2F953B, 0x2AEF7DAD, 0x5B6E2F84,
    0x1521B628, 0x29076170, 0xECDD4775, 0x619F1510, 0x13CCA830, 0xEB61BD96, 0x0334FE1E, 0xAA0363CF,
    0xB5735C90, 0x4C70A239, 0xD59E9E0B, 0xCBAADE14, 0xEECC86BC, 0x60622CA7, 0x9CAB5CAB, 0xB2F3846E,
    0x648B1EAF, 0x19BDF0CA, 0xA02369B9, 0x655ABB50, 0x40685A32, 0x3C2AB4B3, 0x319EE9D5, 0xC021B8F7,
    0x9B540B19, 0x875FA099, 0x95F7997E, 0x623D7DA8, 0xF837889A, 0x97E32D77, 0x11ED935F, 0x16681281,
    0x0E358829, 0xC7E61FD6, 0x96DEDFA1, 0x7858BA99, 0x57F584A5, 0x1B227263, 0x9B83C3FF, 0x1AC24696,
    0xCDB30AEB, 0x532E3054, 0x8FD948E4, 0x6DBC3128, 0x58EBF2EF, 0x34C6FFEA, 0xFE28ED61, 0xEE7C3C73,
    0x5D4A14D9, 0xE864B7E3, 0x42105D14, 0x203E13E0, 0x45EEE2B6, 0xA3AAABEA, 0xDB6C4F15, 0xFACB4FD0,
    0xC742F442, 0xEF6ABBB5, 0x654F3B1D, 0x41CD2105, 0xD81E799E, 0x86854DC7, 0xE44B476A, 0x3D816250,
    0xCF62A1F2, 0x5B8D2646, 0xFC8883A0, 0xC1C7B6A3, 0x7F1524C3, 0x69CB7492, 0x47848A0B, 0x5692B285,
    0x095BBF00, 0xAD19489D, 0x1462B174, 0x23820E00, 0x58428D2A, 0x0C55F5EA, 0x1DADF43E, 0x233F7061,
    0x3372F092, 0x8D937E41, 0xD65FECF1, 0x6C223BDB, 0x7CDE3759, 0xCBEE7460, 0x4085F2A7, 0xCE77326E,
    0xA6078084, 0x19F8509E, 0xE8EFD855, 0x61D99735, 0xA969A7AA, 0xC50C06C2, 0x5A04ABFC, 0x800BCADC,
    0x9E447A2E, 0xC3453484, 0xFDD56705, 0x0E1E9EC9, 0xDB73DBD3, 0x105588CD, 0x675FDA79, 0xE3674340,
    0xC5C43465, 0x713E38D8, 0x3D28F89E, 0xF16DFF20, 0x153E21E7, 0x8FB03D4A, 0xE6E39F2B, 0xDB83ADF7
    ],
    [
    0xE93D5A68, 0x948140F7, 0xF64C261C, 0x94692934, 0x411520F7, 0x7602D4F7, 0xBCF46B2E, 0xD4A20068,
    0xD4082471, 0x3320F46A, 0x43B7D4B7, 0x500061AF, 0x1E39F62E, 0x97244546, 0x14214F74, 0xBF8B8840,
    0x4D95FC1D, 0x96B591AF, 0x70F4DDD3, 0x66A02F45, 0xBFBC09EC, 0x03BD9785, 0x7FAC6DD0, 0x31CB8504,
    0x96EB27B3, 0x55FD3941, 0xDA2547E6, 0xABCA0A9A, 0x28507825, 0x530429F4, 0x0A2C86DA, 0xE9B66DFB,
    0x68DC1462, 0xD7486900, 0x680EC0A4, 0x27A18DEE, 0x4F3FFEA2, 0xE887AD8C, 0xB58CE006, 0x7AF4D6B6,
    0xAACE1E7C, 0xD3375FEC, 0xCE78A399, 0x406B2A42, 0x20FE9E35, 0xD9F385B9, 0xEE39D7AB, 0x3B124E8B,
    0x1DC9FAF7, 0x4B6D1856, 0x26A36631, 0xEAE397B2, 0x3A6EFA74, 0xDD5B4332, 0x6841E7F7, 0xCA7820FB,
    0xFB0AF54E, 0xD8FEB397, 0x454056AC, 0xBA489527, 0x55533A3A, 0x20838D87, 0xFE6BA9B7, 0xD096954B,
    0x55A867BC, 0xA1159A58, 0xCCA92963, 0x99E1DB33, 0xA62A4A56, 0x3F3125F9, 0x5EF47E1C, 0x9029317C,
    0xFDF8E802, 0x04272F70, 0x80BB155C, 0x05282CE3, 0x95C11548, 0xE4C66D22, 0x48C1133F, 0xC70F86DC,
    0x07F9C9EE, 0x41041F0F, 0x404779A4, 0x5D886E17, 0x325F51EB, 0xD59BC0D1, 0xF2BCC18F, 0x41113564,
    0x257B7834, 0x602A9C60, 0xDFF8E8A3, 0x1F636C1B, 0x0E12B4C2, 0x02E1329E, 0xAF664FD1, 0xCAD18115,
    0x6B2395E0, 0x333E92E1, 0x3B240B62, 0xEEBEB922, 0x85B2A20E, 0xE6BA0D99, 0xDE720C8C, 0x2DA2F728,
    0xD0127845, 0x95B794FD, 0x647D0862, 0xE7CCF5F0, 0x5449A36F, 0x877D48FA, 0xC39DFD27, 0xF33E8D1E,
    0x0A476341, 0x992EFF74, 0x3A6F6EAB, 0xF4F8FD37, 0xA812DC60, 0xA1EBDDF8, 0x991BE14C, 0xDB6E6B0D,
    0xC67B5510, 0x6D672C37, 0x2765D43B, 0xDCD0E804, 0xF1290DC7, 0xCC00FFA3, 0xB5390F92, 0x690FED0B,
    0x667B9FFB, 0xCEDB7D9C, 0xA091CF0B, 0xD9155EA3, 0xBB132F88, 0x515BAD24, 0x7B9479BF, 0x763BD6EB,
    0x37392EB3, 0xCC115979, 0x8026E297, 0xF42E312D, 0x6842ADA7, 0xC66A2B3B, 0x12754CCC, 0x782EF11C,
    0x6A124237, 0xB79251E7, 0x06A1BBE6, 0x4BFB6350, 0x1A6B1018, 0x11CAEDFA, 0x3D25BDD8, 0xE2E1C3C9,
    0x44421659, 0x0A121386, 0xD90CEC6E, 0xD5ABEA2A, 0x64AF674E, 0xDA86A85F, 0xBEBFE988, 0x64E4C3FE,
    0x9DBC8057, 0xF0F7C086, 0x60787BF8, 0x6003604D, 0xD1FD8346, 0xF6381FB0, 0x7745AE04, 0xD736FCCC,
    0x83426B33, 0xF01EAB71, 0xB0804187, 0x3C005E5F, 0x77A057BE, 0xBDE8AE24, 0x55464299, 0xBF582E61,
    0x4E58F48F, 0xF2DDFDA2, 0xF474EF38, 0x8789BDC2, 0x5366F9C3, 0xC8B38E74, 0xB475F255, 0x46FCD9B9,
    0x7AEB2661, 0x8B1DDF84, 0x846A0E79, 0x915F95E2, 0x466E598E, 0x20B45770, 0x8CD55591, 0xC902DE4C,
    0xB90BACE1, 0xBB8205D0, 0x11A86248, 0x7574A99E, 0xB77F19B6, 0xE0A9DC09, 0x662D09A1, 0xC4324633,
    0xE85A1F02, 0x09F0BE8C, 0x4A99A025, 0x1D6EFE10, 0x1AB93D1D, 0x0BA5A4DF, 0xA186F20F, 0x2868F169,
    0xDCB7DA83, 0x573906FE, 0xA1E2CE9B, 0x4FCD7F52, 0x50115E01, 0xA70683FA, 0xA002B5C4, 0x0DE6D027,
    0x9AF88C27, 0x773F8641, 0xC3604C06, 0x61A806B5, 0xF0177A28, 0xC0F586E0, 0x006058AA, 0x30DC7D62,
    0x11E69ED7, 0x2338EA63, 0x53C2DD94, 0xC2C21634, 0xBBCBEE56, 0x90BCB6DE, 0xEBFC7DA1, 0xCE591D76,
    0x6F05E409, 0x4B7C0188, 0x39720A3D, 0x7C927C24, 0x86E3725F, 0x724D9DB9, 0x1AC15BB4, 0xD39EB8FC,
    0xED545578, 0x08FCA5B5, 0xD83D7CD3, 0x4DAD0FC4, 0x1E50EF5E, 0xB161E6F8, 0xA28514D9, 0x6C51133C,
    0x6FD5C7E7, 0x56E14EC4, 0x362ABFCE, 0xDDC6C837, 0xD79A3234, 0x92638212, 0x670EFA8E, 0x406000E0
    ],
    [
    0x3A39CE37, 0xD3FAF5CF, 0xABC27737, 0x5AC52D1B, 0x5CB0679E, 0x4FA33742, 0xD3822740, 0x99BC9BBE,
    0xD5118E9D, 0xBF0F7315, 0xD62D1C7E, 0xC700C47B, 0xB78C1B6B, 0x21A19045, 0xB26EB1BE, 0x6A366EB4,
    0x5748AB2F, 0xBC946E79, 0xC6A376D2, 0x6549C2C8, 0x530FF8EE, 0x468DDE7D, 0xD5730A1D, 0x4CD04DC6,
    0x2939BBDB, 0xA9BA4650, 0xAC9526E8, 0xBE5EE304, 0xA1FAD5F0, 0x6A2D519A, 0x63EF8CE2, 0x9A86EE22,
    0xC089C2B8, 0x43242EF6, 0xA51E03AA, 0x9CF2D0A4, 0x83C061BA, 0x9BE96A4D, 0x8FE51550, 0xBA645BD6,
    0x2826A2F9, 0xA73A3AE1, 0x4BA99586, 0xEF5562E9, 0xC72FEFD3, 0xF752F7DA, 0x3F046F69, 0x77FA0A59,
    0x80E4A915, 0x87B08601, 0x9B09E6AD, 0x3B3EE593, 0xE990FD5A, 0x9E34D797, 0x2CF0B7D9, 0x022B8B51,
    0x96D5AC3A, 0x017DA67D, 0xD1CF3ED6, 0x7C7D2D28, 0x1F9F25CF, 0xADF2B89B, 0x5AD6B472, 0x5A88F54C,
    0xE029AC71, 0xE019A5E6, 0x47B0ACFD, 0xED93FA9B, 0xE8D3C48D, 0x283B57CC, 0xF8D56629, 0x79132E28,
    0x785F0191, 0xED756055, 0xF7960E44, 0xE3D35E8C, 0x15056DD4, 0x88F46DBA, 0x03A16125, 0x0564F0BD,
    0xC3EB9E15, 0x3C9057A2, 0x97271AEC, 0xA93A072A, 0x1B3F6D9B, 0x1E6321F5, 0xF59C66FB, 0x26DCF319,
    0x7533D928, 0xB155FDF5, 0x03563482, 0x8ABA3CBB, 0x28517711, 0xC20AD9F8, 0xABCC5167, 0xCCAD925F,
    0x4DE81751, 0x3830DC8E, 0x379D5862, 0x9320F991, 0xEA7A90C2, 0xFB3E7BCE, 0x5121CE64, 0x774FBE32,
    0xA8B6E37E, 0xC3293D46, 0x48DE5369, 0x6413E680, 0xA2AE0810, 0xDD6DB224, 0x69852DFD, 0x09072166,
    0xB39A460A, 0x6445C0DD, 0x586CDECF, 0x1C20C8AE, 0x5BBEF7DD, 0x1B588D40, 0xCCD2017F, 0x6BB4E3BB,
    0xDDA26A7E, 0x3A59FF45, 0x3E350A44, 0xBCB4CDD5, 0x72EACEA8, 0xFA6484BB, 0x8D6612AE, 0xBF3C6F47,
    0xD29BE463, 0x542F5D9E, 0xAEC2771B, 0xF64E6370, 0x740E0D8D, 0xE75B1357, 0xF8721671, 0xAF537D5D,
    0x4040CB08, 0x4EB4E2CC, 0x34D2466A, 0x0115AF84, 0xE1B00428, 0x95983A1D, 0x06B89FB4, 0xCE6EA048,
    0x6F3F3B82, 0x3520AB82, 0x011A1D4B, 0x277227F8, 0x611560B1, 0xE7933FDC, 0xBB3A792B, 0x344525BD,
    0xA08839E1, 0x51CE794B, 0x2F32C9B7, 0xA01FBAC9, 0xE01CC87E, 0xBCC7D1F6, 0xCF0111C3, 0xA1E8AAC7,
    0x1A908749, 0xD44FBD9A, 0xD0DADECB, 0xD50ADA38, 0x0339C32A, 0xC6913667, 0x8DF9317C, 0xE0B12B4F,
    0xF79E59B7, 0x43F5BB3A, 0xF2D519FF, 0x27D9459C, 0xBF97222C, 0x15E6FC2A, 0x0F91FC71, 0x9B941525,
    0xFAE59361, 0xCEB69CEB, 0xC2A86459, 0x12BAA8D1, 0xB6C1075E, 0xE3056A0C, 0x10D25065, 0xCB03A442,
    0xE0EC6E0E, 0x1698DB3B, 0x4C98A0BE, 0x3278E964, 0x9F1F9532, 0xE0D392DF, 0xD3A0342B, 0x8971F21E,
    0x1B0A7441, 0x4BA3348C, 0xC5BE7120, 0xC37632D8, 0xDF359F8D, 0x9B992F2E, 0xE60B6F47, 0x0FE3F11D,
    0xE54CDA54, 0x1EDAD891, 0xCE6279CF, 0xCD3E7E6F, 0x1618B166, 0xFD2C1D05, 0x848FD2C5, 0xF6FB2299,
    0xF523F357, 0xA6327623, 0x93A83531, 0x56CCCD02, 0xACF08162, 0x5A75EBB5, 0x6E163697, 0x88D273CC,
    0xDE966292, 0x81B949D0, 0x4C50901B, 0x71C65614, 0xE6C6C7BD, 0x327A140A, 0x45E1D006, 0xC3F27B9A,
    0xC9AA53FD, 0x62A80F00, 0xBB25BFE2, 0x35BDD2F6, 0x71126905, 0xB2040222, 0xB6CBCF7C, 0xCD769C2B,
    0x53113EC0, 0x1640E3D3, 0x38ABBD60, 0x2547ADF0, 0xBA38209C, 0xF746CE76, 0x77AFA1C5, 0x20756060,
    0x85CBFE4E, 0x8AE88DD8, 0x7AAAF9B0, 0x4CF9AA7E, 0x1948C25C, 0x02FB8A8C, 0x01C36AE4, 0xD6EBE1F9,
    0x90D4F869, 0xA65CDEA0, 0x3F09252D, 0xC208E69F, 0xB74E6132, 0xCE77E25B, 0x578FDFE3, 0x3AC372E6
    ],
]

class Blowfish:
    def __init__(s, key):
        s.P = P0[:]; s.S = [x[:] for x in S0]; ki = 0
        for i in range(18):
            v = 0
            for _ in range(4):
                v = ((v << 8) | key[ki]) & M32; ki = (ki + 1) % len(key)
            s.P[i] ^= v
        l = r = 0
        for i in range(0, 18, 2):
            l, r = s.enc(l, r); s.P[i], s.P[i + 1] = l, r
        for i in range(4):
            for x in range(0, 256, 2):
                l, r = s.enc(l, r); s.S[i][x], s.S[i][x + 1] = l, r
    def F(s, v):
        S = s.S
        return ((((S[0][v >> 24] + S[1][(v >> 16) & 255]) & M32) ^ S[2][(v >> 8) & 255]) + S[3][v & 255]) & M32
    def enc(s, l, r):
        for i in range(16):
            l ^= s.P[i]; r = s.F(l) ^ r; l, r = r, l
        l, r = r, l
        return l ^ s.P[17], r ^ s.P[16]
    def dec(s, l, r):
        for i in range(17, 1, -1):
            l ^= s.P[i]; r = s.F(l) ^ r; l, r = r, l
        l, r = r, l
        return l ^ s.P[0], r ^ s.P[1]

class MT:
    def __init__(s, seed):
        s.st = [seed & M32]
        for i in range(1, 624):
            p = s.st[-1]; s.st.append((i + 0x6C078965 * (p ^ (p >> 30))) & M32)
        s.pos = 624
    def twist(s):
        st = s.st
        for i in range(624):
            x = st[i]; y = st[(i + 1) % 624]
            v = (x & 0x80000000) | (y & 0x7FFFFFFF)
            st[i] = st[(i + 397) % 624] ^ (v >> 1) ^ (0x9908B0DF if y & 1 else 0)
        s.pos = 0
    def nxt(s):
        if s.pos >= 624: s.twist()
        n = s.st[s.pos]; s.pos += 1
        a = (((((n >> 11) ^ n) & 0xFF3A58AD) << 7) & M32) ^ (n >> 11) ^ n
        b = (((a & 0xFFFFDF8C) << 15) & M32) ^ a
        return b ^ (b >> 18)

def decrypt_save(raw):
    seed = struct.unpack_from("<I", raw, 0x14)[0]
    data = bytearray(raw[DATA_OFF:]); n = len(data)
    mt = MT(seed)
    key = b"".join(struct.pack("<I", mt.nxt()) for _ in range(14))   # 56-byte Blowfish key
    for i in range(n // 4):
        struct.pack_into("<I", data, i * 4, struct.unpack_from("<I", data, i * 4)[0] ^ mt.nxt())
    bf = Blowfish(key)
    for i in range(n // 8):
        l, r = struct.unpack_from("<II", data, i * 8)
        struct.pack_into("<II", data, i * 8, *bf.dec(l, r))
    return bytes(data)

def encrypt_save(plain, seed):
    """Inverse of decrypt_save: Blowfish-encrypt every 8-byte block first, then XOR with the MT output (same seed, same key)."""
    n = len(plain); data = bytearray(plain)
    mt = MT(seed)
    key = b"".join(struct.pack("<I", mt.nxt()) for _ in range(14))
    bf = Blowfish(key)
    for i in range(n // 8):
        l, r = struct.unpack_from("<II", data, i * 8)
        struct.pack_into("<II", data, i * 8, *bf.enc(l, r))
    for i in range(n // 4):
        struct.pack_into("<I", data, i * 4, struct.unpack_from("<I", data, i * 4)[0] ^ mt.nxt())
    return bytes(data)

# ---------------- SaveMeta / scanning ----------------
NAME_RE = re.compile(r"^(\d+)\. (?:CHAPTER (\d+)|(MISSION)) (\d+):(\d+)$")

def read_meta_name(path):
    raw = open(path, "rb").read()
    txt = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-16-le")
    m = re.search(r"Name=(.*?)\r?\n", txt + "\n")
    return m.group(1) if m else ""

def inspect(folder):
    meta = os.path.join(folder, "SaveMeta.xbx"); dat = os.path.join(folder, "save000.dat")
    if not (os.path.isfile(meta) and os.path.isfile(dat)): return None
    fid = os.path.basename(folder.rstrip("/\\")).upper()
    name = read_meta_name(meta)
    info = {"folder": fid, "name": name, "hash_ok": folder_id(name) == fid, "path": folder,
            "modified": os.path.getmtime(dat)}
    m = NAME_RE.match(name)
    if m:
        info["slot"] = int(m.group(1))
        info["kind"] = "Mission" if m.group(3) else "Chapter"
        if m.group(2): info["chapter"] = int(m.group(2))
        info["time_label"] = "%s:%s" % (m.group(4), m.group(5))      # HHH:MM
    raw = open(dat, "rb").read()
    if len(raw) == SAVE_SIZE:
        d = decrypt_save(raw)
        info["decrypt_ok"] = d[-6:] == TAIL
        if info["decrypt_ok"]:
            fr = struct.unpack_from("<I", d, OFF_PLAYTIME)[0]
            s = fr // 60
            info["playtime"] = "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)
            info["difficulty"] = DIFFICULTY.get(d[OFF_DIFFICULTY], "?%d" % d[OFF_DIFFICULTY])
            info["chapter_from_dat"] = d[OFF_CHAPTER0] + 1
            info["save_point_raw"] = d[OFF_SAVEPOINT]
            info["karma"] = struct.unpack_from("<I", d, OFF_KARMA)[0]
    return info



# ---------------- slot moving (rename SaveMeta Name + folder; save000.dat is untouched) ----------------
import shutil

def backup_root(root):
    """Copy the whole 5443000d folder into <app folder>\\backups\\ (never inside UDATA). Returns the backup path."""
    base = os.path.join(APP_DIR, "backups"); os.makedirs(base, exist_ok=True)
    dst = os.path.join(base, "%s_%s" % (os.path.basename(root.rstrip("/\\")), time.strftime("%Y%m%d_%H%M%S")))
    shutil.copytree(root, dst)
    return dst

def _plan_move(root, folder, new_slot):
    path = os.path.join(root, folder)
    name = read_meta_name(os.path.join(path, "SaveMeta.xbx"))
    m = NAME_RE.match(name)
    if not m: raise ValueError(t("存档名格式不认识: %r") % name)
    new_name = "%d.%s" % (new_slot, name.split(".", 1)[1])
    return path, name, new_name, os.path.join(root, folder_id(new_name))

def _write_meta_name(meta_path, new_name):
    raw = open(meta_path, "rb").read()
    txt = raw.decode("utf-16")
    new_txt = re.sub(r"Name=.*?(?=\r?\n|$)", lambda _: "Name=" + new_name, txt, count=1)
    tmp = meta_path + ".tmp"
    with open(tmp, "wb") as f: f.write(b"\xff\xfe" + new_txt.lstrip("\ufeff").encode("utf-16-le"))
    os.replace(tmp, meta_path)

def move_slot(root, folder, new_slot, extra=None):
    """Change a save's slot number. extra=(folder2, slot2) performs a swap atomically-ish (both validated first)."""
    jobs = [(folder, new_slot)] + ([extra] if extra else [])
    plans = [_plan_move(root, f, sl) + (f,) for f, sl in jobs]
    news = [p[3] for p in plans]
    if len(set(os.path.normcase(n) for n in news)) != len(news): raise ValueError(t("两个存档会得到相同的文件夹名"))
    olds = set(os.path.normcase(p[0]) for p in plans)
    for p in plans:
        if os.path.exists(p[3]) and os.path.normcase(p[3]) not in olds:
            raise ValueError(t("目标文件夹已存在: ") + os.path.basename(p[3]))
    # two-phase: write metas, then rename via temp names (handles swap without collisions)
    done = []
    try:
        for path, name, new_name, new_path, f in plans:
            _write_meta_name(os.path.join(path, "SaveMeta.xbx"), new_name); done.append((path, name))
        temps = []
        for path, name, new_name, new_path, f in plans:
            tmp = path + ".__moving__"; os.rename(path, tmp); temps.append((tmp, new_path))
        for tmp, new_path in temps: os.rename(tmp, new_path)
    except Exception:
        for path, name in done:                     # best-effort rollback of the meta text
            for cand in (path, path + ".__moving__"):
                if os.path.isdir(cand):
                    try: _write_meta_name(os.path.join(cand, "SaveMeta.xbx"), name)
                    except Exception: pass
        for tmp in [p[0] + ".__moving__" for p in plans]:
            if os.path.isdir(tmp) and not os.path.exists(tmp[:-len(".__moving__")]):
                os.rename(tmp, tmp[:-len(".__moving__")])
        raise
    out = []
    for path, name, new_name, new_path, f in plans:
        r = inspect(new_path)
        if not r or not r["hash_ok"] or r.get("slot") != int(new_name.split(".")[0]): raise RuntimeError(t("改完后校验失败: ") + new_path)
        out.append(r)
    return out


# ---------------- HD key signing (XCalculateSignature, non-roamable) ----------------
import hmac, hashlib
XBOX_CERT_KEY = bytes.fromhex("5C0733AE0401F7E8BA7993FDCD2F1FE0")
NGB_TITLE_KEY = bytes.fromhex("FC3376488B3E5F00F65A6BDA9209CFE8")        # Ninja Gaiden Black signature key
NG_TITLE_KEY = bytes.fromhex("A50114CA2B7C8198E829E7C937D6FC40")         # original Ninja Gaiden (alt key)

def _hmac(k, d): return hmac.new(k, d, hashlib.sha1).digest()

def roamable_sig(raw, title_key=NGB_TITLE_KEY):
    return _hmac(_hmac(XBOX_CERT_KEY, title_key)[:16], raw[0x14:])

def sign_raw(raw, hd_key, title_key=NGB_TITLE_KEY):
    """Return raw with bytes 0..0x14 replaced by the non-roamable signature for hd_key (16 bytes)."""
    return _hmac(hd_key, roamable_sig(raw, title_key)) + raw[0x14:]

def sig_owner(raw, keys):
    """Name of the first HD key (dict name -> 16 bytes) whose signature matches the file, else ''. """
    if len(raw) not in (SAVE_SIZE, SYSTEM_SIZE): return ""
    roam = roamable_sig(raw)
    for name, k in keys.items():
        if _hmac(k, roam) == raw[:0x14]: return name
    return ""

def parse_hd_key(text):
    hx = re.sub(r"[\s-]", "", text or "")
    if not re.fullmatch(r"[0-9A-Fa-f]{32}", hx): raise ValueError(t("HD key 需要 32 个十六进制字符"))
    return bytes.fromhex(hx)

def resign_saves(root, folders, hd_key, out_root):
    """Copy root-level title files + the chosen save folders into out_root with the save000.dat re-signed. Originals untouched."""
    if os.path.exists(out_root) and os.listdir(out_root): raise ValueError(t("输出文件夹不为空: ") + out_root)
    os.makedirs(out_root, exist_ok=True)
    for e in os.listdir(root):
        p = os.path.join(root, e)
        if os.path.isfile(p): shutil.copy2(p, os.path.join(out_root, e))
    results = []
    for f in folders:
        dst = os.path.join(out_root, f); shutil.copytree(os.path.join(root, f), dst)
        dat = os.path.join(dst, "save000.dat"); raw = open(dat, "rb").read()
        if len(raw) != SAVE_SIZE: results.append((f, False, t("大小不对，已原样复制"))); continue
        new = sign_raw(raw, hd_key)
        with open(dat, "wb") as fh: fh.write(new)
        ok = _hmac(hd_key, roamable_sig(new)) == new[:0x14] and new[0x14:] == raw[0x14:]
        results.append((f, ok, "" if ok else t("验证失败")))
    return results

def find_system_dat(root):
    """TDATA\\5443000d\\system.dat belonging to a UDATA\\5443000d root, or None."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(root.rstrip("/\\"))))
    for td in ("TDATA", "tdata"):
        for i in ("5443000d", "5443000D"):
            p = os.path.join(base, td, i, "system.dat")
            if os.path.isfile(p): return p
    return None

def resign_system_dat(src, hd_key, out_file):
    """Re-sign TDATA system.dat (0x550 bytes) into out_file. Returns (ok, msg)."""
    raw = open(src, "rb").read()
    if len(raw) != SYSTEM_SIZE: return False, t("system.dat 大小不对(%d)，未处理") % len(raw)
    new = sign_raw(raw, hd_key)
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "wb") as fh: fh.write(new)
    ok = _hmac(hd_key, roamable_sig(new)) == new[:0x14] and new[0x14:] == raw[0x14:]
    return ok, "" if ok else t("验证失败")


# ---------------- batch copy / clipboard ----------------
def copy_saves(root, folders, dest, with_title_files=False):
    """Copy save folders (given in the order you want them to appear) into dest.
    Folder mtimes are set ascending in that order, so tools/games that list by creation/modify time keep slot order."""
    base = os.path.join(dest, os.path.basename(root.rstrip("/\\"))) if with_title_files else dest
    os.makedirs(base, exist_ok=True)
    if with_title_files:
        for e in os.listdir(root):
            p = os.path.join(root, e)
            if os.path.isfile(p) and not os.path.exists(os.path.join(base, e)): shutil.copy2(p, os.path.join(base, e))
    t0 = time.time() - len(folders) - 1
    results = []
    for i, f in enumerate(folders):
        dst = os.path.join(base, f)
        if os.path.exists(dst): results.append((f, False, t("目标已存在，已跳过"))); continue
        shutil.copytree(os.path.join(root, f), dst)
        mt = t0 + i
        for dp, dn, fn in os.walk(dst, topdown=False):
            for n in fn: os.utime(os.path.join(dp, n), (mt, mt))
            os.utime(dp, (mt, mt))
        results.append((f, True, ""))
    return base, results

def build_hdrop(paths):
    """DROPFILES structure (wide chars) as used by the Windows CF_HDROP clipboard format."""
    files = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    return struct.pack("<IiiII", 20, 0, 0, 0, 1) + files

def set_clipboard_files(paths):
    """Windows only: put folders on the clipboard as a file copy, so Explorer's Ctrl+V pastes them."""
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p; k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalLock.restype = ctypes.c_void_p; k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    u32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]; u32.SetClipboardData.restype = ctypes.c_void_p
    u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    def put(fmt, data):
        h = k32.GlobalAlloc(0x0042, len(data))                     # GMEM_MOVEABLE | GMEM_ZEROINIT
        p = k32.GlobalLock(h); ctypes.memmove(p, data, len(data)); k32.GlobalUnlock(h)
        if not u32.SetClipboardData(fmt, h): raise OSError(t("SetClipboardData 失败"))
    if not u32.OpenClipboard(None): raise OSError(t("无法打开剪贴板"))
    try:
        u32.EmptyClipboard()
        put(15, build_hdrop(paths))                                  # CF_HDROP
        put(u32.RegisterClipboardFormatW("Preferred DropEffect"), struct.pack("<I", 1))   # DROPEFFECT_COPY
    finally:
        u32.CloseClipboard()

# =====================================================================================
#  GUI
# =====================================================================================
import time, tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else os.getcwd()
NOTES_FILE = os.path.join(APP_DIR, "save_notes.json")      # user notes: {"<folder id>": "note"}
KEYS_FILE = os.path.join(APP_DIR, "hd_keys.json")          # user editable: {"name": "32 hex chars"}
DEFAULT_KEYS = {}   # no keys are bundled: add your own in hd_keys.json (git-ignored) or via the GUI

def load_keys():
    data = load_json(KEYS_FILE, None)
    if data is None:
        data = dict(DEFAULT_KEYS)
        try: save_json(KEYS_FILE, data)
        except Exception: pass
    keys = {}
    for n, h in data.items():
        try: keys[n] = parse_hd_key(h)
        except Exception: pass
    return keys

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=1)

def find_save_root(path):
    """Accept ...\\5443000d, its parent (UDATA), or a folder that contains UDATA."""
    cands = [path, os.path.join(path, "5443000d"), os.path.join(path, "5443000D"),
             os.path.join(path, "UDATA", "5443000d"), os.path.join(path, "UDATA", "5443000D")]
    for c in cands:
        if os.path.isdir(c) and any(os.path.isfile(os.path.join(c, e, "SaveMeta.xbx")) for e in os.listdir(c) if os.path.isdir(os.path.join(c, e))):
            return c
    return None

COLUMNS = [  # key, title, width, anchor
    ("slot", "槽位", 50, "center"), ("kind", "模式", 70, "center"), ("chapter", "章节", 50, "center"),
    ("time_label", "存档时间 HHH:MM", 135, "center"),
    ("playtime", "精确游玩时间", 90, "center"), ("difficulty", "难度", 95, "center"), ("karma", "Karma", 80, "center"),
    ("save_point_raw", "存档点ID(原始)", 115, "center"), ("modified", "文件修改时间", 130, "center"),
    ("folder", "文件夹名", 125, "center"), ("signed_by", "签名属于(HD Key)", 130, "center"), ("check", "校验", 70, "center"), ("note", "备注", 200, "w")]

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("1280x620"); self.minsize(900, 400)
        self.keys = {}; self.backup_done = None; self.rows = []; self.root_dir = None; self.sort_key = "slot"; self.sort_rev = False
        self.notes = load_json(NOTES_FILE, {})
        self.q = tk.StringVar(); self.q.trace_add("write", lambda *a: self.fill())
        self.build_ui()
        self.after(200, self.try_auto)

    def switch_lang(self):
        import ngb_i18n
        set_lang("en" if ngb_i18n.LANG == "zh" else "zh")
        for w in self.winfo_children(): w.destroy()
        self.build_ui()
        if self.root_dir: self.load(self.root_dir)

    def build_ui(self):
        self.title(t("忍者外传 黑之章 存档管理器 (Xbox / 5443000D)"))
        top = ttk.Frame(self, padding=6); top.pack(fill="x")
        ttk.Button(top, text=t("选择存档文件夹…"), command=self.choose).pack(side="left")
        ttk.Button(top, text=t("刷新"), command=self.reload).pack(side="left", padx=4)
        ttk.Button(top, text=t("导出 CSV…"), command=self.export_csv).pack(side="left")
        ttk.Button(top, text=t("编辑备注"), command=self.edit_note).pack(side="left", padx=4)
        ttk.Button(top, text=t("移动到槽位…"), command=self.move_dialog).pack(side="left", padx=4)
        ttk.Button(top, text=t("HD Key 重签…"), command=self.resign_dialog).pack(side="left")
        ttk.Button(top, text=t("system.dat 重签…"), command=self.system_dialog).pack(side="left", padx=4)
        ttk.Button(top, text=t("system.dat 更新…"), command=self.sysupdate_dialog).pack(side="left")
        ttk.Button(top, text=t("打开所选存档文件夹"), command=self.open_folder).pack(side="left", padx=4)
        ttk.Label(top, text=t("筛选:")).pack(side="left", padx=(14, 2))
        ttk.Entry(top, textvariable=self.q, width=18).pack(side="left")
        self.path_lbl = ttk.Label(top, text=t("（未选择）"), foreground="#666"); self.path_lbl.pack(side="left", padx=12)
        top2 = ttk.Frame(self, padding=(6, 0, 6, 4)); top2.pack(fill="x")
        ttk.Button(top2, text=t("全选 (Ctrl+A)"), command=self.select_all).pack(side="left")
        ttk.Button(top2, text=t("复制所选到…"), command=self.copy_dialog).pack(side="left", padx=4)
        ttk.Button(top2, text=t("复制所选到剪贴板（资源管理器 Ctrl+V 粘贴）"), command=self.copy_clip).pack(side="left")
        ttk.Button(top2, text=t("删除所选 (Del)"), command=self.delete_selected).pack(side="left", padx=4)
        ttk.Label(top2, text=t("Ctrl/Shift 多选"), foreground="#666").pack(side="left", padx=10)
        frm = ttk.Frame(self); frm.pack(fill="both", expand=True, padx=6)
        self.tree = ttk.Treeview(frm, columns=[c[0] for c in COLUMNS], show="headings", selectmode="extended")
        for k, ttl, w, a in COLUMNS:
            self.tree.heading(k, text=t(ttl), command=lambda k=k: self.sort_by(k))
            self.tree.column(k, width=w, anchor=a, stretch=(k == "note"))
        vs = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview); self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True); vs.pack(side="right", fill="y")
        self.tree.tag_configure("bad", foreground="#b00020"); self.tree.tag_configure("odd", background="#f4f6fa")
        self.tree.bind("<<TreeviewSelect>>", self.on_select); self.tree.bind("<Double-1>", self.on_double); self.tree.bind("<Delete>", self.delete_selected);self.tree.bind("<Control-a>", self.select_all); self.tree.bind("<Control-A>", self.select_all); self.tree.bind("<Button-3>", self.popup); self.tree.bind("<Button-2>", self.popup)
        self.detail = tk.Text(self, height=5, wrap="word", state="disabled", background="#fafafa"); self.detail.pack(fill="x", padx=6, pady=6)
        bottom = ttk.Frame(self); bottom.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Button(bottom, text=t("English"), command=self.switch_lang, width=8).pack(side="right")      # bottom-right so it is never clipped on small screens
        self.status = ttk.Label(bottom, text="", anchor="w"); self.status.pack(side="left", fill="x", expand=True)
        if self.root_dir: self.path_lbl.config(text=self.root_dir)

    def try_auto(self):
        for p in sys.argv[1:2] + [os.getcwd(), APP_DIR]:
            r = find_save_root(p) if p else None
            if r: self.load(r); return

    def choose(self):
        p = filedialog.askdirectory(title=t("选择 UDATA\\5443000d 文件夹（或其上级）"))
        if not p: return
        r = find_save_root(p)
        if not r: messagebox.showwarning(t("未找到存档"), t("这个文件夹里没有找到含 SaveMeta.xbx 的存档子文件夹。\n请选择 UDATA\\5443000d。")); return
        self.load(r)

    def reload(self):
        if self.root_dir: self.load(self.root_dir)

    def load(self, root):
        self.root_dir = root; self.path_lbl.config(text=root)
        self.notes = load_json(NOTES_FILE, {}); self.keys = load_keys()
        rows = []
        for e in sorted(os.listdir(root)):
            p = os.path.join(root, e)
            if os.path.isdir(p):
                try: r = inspect(p)
                except Exception as ex: r = {"folder": e.upper(), "name": t("(读取失败: %s)") % ex, "hash_ok": False, "path": p}
                if r:
                    try: r["signed_by"] = sig_owner(open(os.path.join(p, "save000.dat"), "rb").read(), self.keys) or t("未识别")
                    except Exception: r["signed_by"] = "?"
                    rows.append(r)
        self.rows = rows; self.fill()

    def cell(self, r, k):
        if k == "check":
            if r.get("decrypt_ok") is False: return t("解密失败")
            return t("正常") if r.get("hash_ok") else t("名称≠哈希")
        if k == "note": return self.notes.get(r["folder"], "")
        if k == "modified": return time.strftime("%Y-%m-%d %H:%M", time.localtime(r["modified"])) if r.get("modified") else ""
        if k == "save_point_raw":
            v = r.get("save_point_raw"); return "" if v is None else "0x%02X (%d)" % (v, v)
        v = r.get(k); return "" if v is None else v

    def sortval(self, r, k):
        if k in ("slot", "chapter"): return r.get(k, 9999)
        if k == "karma": return r.get("karma", -1)
        if k == "time_label":
            try: h, m = r["time_label"].split(":"); return int(h) * 60 + int(m)
            except Exception: return 0
        if k == "playtime":
            try: h, m, s = map(int, r["playtime"].split(":")); return h * 3600 + m * 60 + s
            except Exception: return 0
        if k == "modified": return r.get("modified", 0)
        if k == "save_point_raw": return r.get("save_point_raw", -1)
        return str(self.cell(r, k))

    def sort_by(self, k):
        self.sort_rev = (not self.sort_rev) if k == self.sort_key else False
        self.sort_key = k; self.fill()

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        q = self.q.get().strip().lower()
        rows = sorted(self.rows, key=lambda r: self.sortval(r, self.sort_key), reverse=self.sort_rev)
        n = 0
        for r in rows:
            vals = [self.cell(r, c[0]) for c in COLUMNS]
            if q and q not in " ".join(str(v) for v in vals).lower(): continue
            tags = ["bad"] if (not r.get("hash_ok") or r.get("decrypt_ok") is False) else (["odd"] if n % 2 else [])
            self.tree.insert("", "end", iid=r["folder"], values=vals, tags=tags); n += 1
        bad = sum(1 for r in self.rows if not r.get("hash_ok"))
        self.status.config(text=t("共 %d 个存档，显示 %d 个%s。点列标题排序，双击一行打开该存档文件夹，右键更多操作。") % (len(self.rows), n, (t("；%d 个文件夹名与存档名哈希不一致（红色）") % bad) if bad else ""))
        self.set_detail("")

    def current(self):
        s = self.tree.selection()
        return next((r for r in self.rows if s and r["folder"] == s[0]), None)

    def selected(self):
        sel = set(self.tree.selection())
        return sorted((r for r in self.rows if r["folder"] in sel), key=lambda r: r.get("slot", 9999))

    def select_all(self, *_):
        self.tree.selection_set(self.tree.get_children()); return "break"

    def set_detail(self, text):
        self.detail.config(state="normal"); self.detail.delete("1.0", "end"); self.detail.insert("1.0", text); self.detail.config(state="disabled")

    def on_select(self, e=None):
        sl = self.selected()
        if len(sl) > 1:
            self.set_detail(t("已选 %d 个存档，槽位: %s\n可以右键或用上方按钮：复制所选到…、复制到剪贴板、HD Key 重签（重签会作用于全部选中的）。") % (len(sl), ", ".join(str(r.get("slot", "?")) for r in sl))); return
        r = self.current()
        if not r: return
        if "frames_check" not in r:       # decoding a save in pure Python takes ~0.25 s, so only do it for the clicked row
            try:
                import ngb_system_dat
                sv = ngb_system_dat.read_save(r["path"])
                r["frames_check"] = t("解码值 %d 帧，旧读法(原始明文 0x16653) %d 帧：%s") % (sv["frames"], sv["legacy"], t("一致") if sv["frames"] == sv["legacy"] else t("不一致"))
            except Exception as ex: r["frames_check"] = t("无法检查 (%s)") % ex
        self.set_detail(t("签名属于: %s\n存档名(SaveMeta Name): %s\n文件夹: %s\n按命名规则由存档名算出的文件夹名: %s  →  %s\n章节(存档名): %s    章节(存档数据): %s\n游玩帧数检查: %s\n路径: %s") % (
            r.get("signed_by", "-"), r.get("name"), r["folder"], folder_id(r.get("name", "")), t("一致") if r.get("hash_ok") else t("不一致"),
            r.get("chapter", "-"), r.get("chapter_from_dat", "-"), r["frames_check"], r.get("path")))

    def edit_note(self):
        r = self.current()
        if not r: return
        win = tk.Toplevel(self); win.title(t("备注 - ") + r["folder"]); win.geometry("420x120"); win.transient(self)
        v = tk.StringVar(value=self.notes.get(r["folder"], "")); e = ttk.Entry(win, textvariable=v); e.pack(fill="x", padx=12, pady=14); e.focus()
        def ok(*_):
            if v.get().strip(): self.notes[r["folder"]] = v.get().strip()
            else: self.notes.pop(r["folder"], None)
            save_json(NOTES_FILE, self.notes); win.destroy(); self.fill(); self.tree.selection_set(r["folder"])
        e.bind("<Return>", ok); ttk.Button(win, text=t("保存"), command=ok).pack()


    def move_dialog(self):
        if len(self.selected()) > 1: messagebox.showinfo(t("移动槽位"), t("移动槽位一次只能选一个存档。")); return
        r = self.current()
        if not r or "slot" not in r: messagebox.showinfo(t("移动槽位"), t("请先选中一个存档。")); return
        win = tk.Toplevel(self); win.title(t("移动到槽位")); win.geometry("360x150"); win.transient(self); win.grab_set()
        ttk.Label(win, text=t("当前槽位 %s（%s）\n移到槽位号:") % (r["slot"], r["folder"])).pack(pady=(12, 4))
        v = tk.StringVar(value=str(r["slot"])); e = ttk.Entry(win, textvariable=v, width=8, justify="center"); e.pack(); e.focus(); e.select_range(0, "end")
        def go(*_):
            try: ns = int(v.get())
            except ValueError: messagebox.showwarning(t("移动槽位"), t("请输入数字。"), parent=win); return
            if ns < 1 or ns == r["slot"]: messagebox.showwarning(t("移动槽位"), t("请输入不同于当前、且大于 0 的槽位号。"), parent=win); return
            if ns > 30 and not messagebox.askyesno(t("移动槽位"), t("你现有存档最大槽位是 30，游戏是否支持超过 30 的槽位还没验证。\n仍要继续吗？"), parent=win): return
            other = next((x for x in self.rows if x.get("slot") == ns), None)
            extra = None
            if other:
                a = messagebox.askyesnocancel(t("槽位已被占用"), t("槽位 %d 已有存档（%s）。\n\n是 = 与它交换位置\n否 = 取消") % (ns, other["folder"]), parent=win)
                if not a: return
                extra = (other["folder"], r["slot"])
            if not self.backup_done:
                try: self.backup_done = backup_root(self.root_dir)
                except Exception as ex: messagebox.showerror(t("备份失败"), t("没有备份就不会修改任何文件。\n%s") % ex, parent=win); return
            try: move_slot(self.root_dir, r["folder"], ns, extra)
            except Exception as ex: messagebox.showerror(t("移动失败"), str(ex), parent=win); return
            win.destroy(); self.load(self.root_dir)
            if messagebox.askyesno(t("完成"), t("已移动到槽位 %d%s。\n备份在:\n%s\n\n提示：读档列表里的游玩时间和顺序存在 TDATA\\5443000d\\system.dat 里，不在存档里。移动槽位后建议顺带更新它（推荐“按整套 UDATA 同步”）。\n现在打开 system.dat 更新窗口吗？") % (ns, t("（并与原占用者交换）") if extra else "", self.backup_done)):
                self.sysupdate_dialog("sync")
        e.bind("<Return>", go); ttk.Button(win, text=t("确定"), command=go).pack(pady=10)


    def resign_dialog(self):
        if not self.rows: messagebox.showinfo(t("重签"), t("请先选择存档文件夹。")); return
        win = tk.Toplevel(self); win.title(t("HD Key 重签")); win.geometry("520x300"); win.transient(self); win.grab_set()
        ttk.Label(win, text=t("把存档重新签名为目标主机的 HD Key（原存档不会被修改，结果写到新文件夹）"), wraplength=480).pack(padx=12, pady=(12, 6), anchor="w")
        f1 = ttk.Frame(win); f1.pack(fill="x", padx=12, pady=4)
        ttk.Label(f1, text=t("目标 HD Key:")).pack(side="left")
        names = list(self.keys) + [t("自定义…")]; cb = ttk.Combobox(f1, values=names, state="readonly", width=18); cb.pack(side="left", padx=6)
        cb.current(0 if self.keys else 0)
        hexv = tk.StringVar(); ent = ttk.Entry(win, textvariable=hexv); ent.pack(fill="x", padx=12)
        def on_pick(*_):
            n = cb.get()
            if n in self.keys: hexv.set(self.keys[n].hex().upper()); ent.state(["readonly"])
            else: hexv.set(""); ent.state(["!readonly"]); ent.focus()
        cb.bind("<<ComboboxSelected>>", on_pick); on_pick()
        nsel = len(self.selected()); scope = tk.StringVar(value="sel" if nsel else "all")
        f2 = ttk.Frame(win); f2.pack(fill="x", padx=12, pady=8)
        ttk.Radiobutton(f2, text=t("只重签选中的存档（%d 个）") % nsel, variable=scope, value="sel").pack(anchor="w")
        ttk.Radiobutton(f2, text=t("重签全部 %d 个存档") % len(self.rows), variable=scope, value="all").pack(anchor="w")
        ttk.Label(win, text=t("可在 hd_keys.json 里增删常用 HD Key。"), foreground="#666").pack(padx=12, anchor="w")
        def go(*_):
            try: key = parse_hd_key(hexv.get())
            except ValueError as ex: messagebox.showwarning(t("重签"), str(ex), parent=win); return
            if scope.get() == "sel":
                folders = [r["folder"] for r in self.selected()]
                if not folders: messagebox.showwarning(t("重签"), t("没有选中的存档。"), parent=win); return
            else: folders = [x["folder"] for x in self.rows]
            tag = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", cb.get() if cb.get() in self.keys else "custom")
            stamp = os.path.join(APP_DIR, "resigned", "%s_%s" % (tag, time.strftime("%Y%m%d_%H%M%S")))
            out = os.path.join(stamp, "UDATA", os.path.basename(self.root_dir.rstrip("/\\")))
            try: res = resign_saves(self.root_dir, folders, key, out)
            except Exception as ex: messagebox.showerror(t("重签失败"), str(ex), parent=win); return
            sysdat = find_system_dat(self.root_dir); extra = ""
            if sysdat:
                try:
                    ok, msg = resign_system_dat(sysdat, key, os.path.join(stamp, "TDATA", "5443000d", "system.dat"))
                    extra = "\nTDATA system.dat: " + (t("已重签") if ok else t("失败 ") + msg)
                except Exception as ex: extra = t("\nTDATA system.dat 失败: %s") % ex
            else: extra = t("\n（未找到 TDATA\\5443000d\\system.dat，仅重签 UDATA）")
            out = stamp
            bad = [x for x in res if not x[1]]
            win.destroy()
            messagebox.showinfo(t("重签完成"), t("成功 %d / %d 个。\n输出文件夹（UDATA / TDATA 子文件夹可直接拷到目标主机）:\n%s%s%s") % (
                len(res) - len(bad), len(res), out, extra, (t("\n\n有问题的: ") + ", ".join("%s(%s)" % (x[0], x[2]) for x in bad)) if bad else ""))
        ttk.Button(win, text=t("开始重签"), command=go).pack(pady=10)

    def system_dialog(self):
        """Standalone window: pick TDATA\\5443000d\\system.dat, show who signed it, re-sign it for another HD key."""
        self.keys = load_keys()
        win = tk.Toplevel(self); win.title(t("TDATA system.dat 重签")); win.geometry("560x330"); win.transient(self); win.grab_set()
        ttk.Label(win, text=t("读取 TDATA\\5443000d\\system.dat（1,360 字节），重签为目标 HD Key（原文件不会被修改）"), wraplength=520).pack(padx=12, pady=(12, 6), anchor="w")
        f0 = ttk.Frame(win); f0.pack(fill="x", padx=12)
        path = tk.StringVar(); ent0 = ttk.Entry(f0, textvariable=path); ent0.pack(side="left", fill="x", expand=True)
        info = ttk.Label(win, text="", foreground="#666", wraplength=520, justify="left")
        def refresh(*_):
            p = path.get().strip()
            if not p: info.config(text=t("请选择 system.dat。")); return
            try: raw = open(p, "rb").read()
            except Exception as ex: info.config(text=t("读取失败: %s") % ex); return
            if len(raw) != SYSTEM_SIZE: info.config(text=t("大小 %d 字节，不是 system.dat（应为 %d）。") % (len(raw), SYSTEM_SIZE)); return
            info.config(text=t("大小正常。当前签名属于: %s") % (sig_owner(raw, self.keys) or t("未识别（不在 hd_keys.json 里）")))
        def browse():
            init = os.path.dirname(find_system_dat(self.root_dir)) if self.root_dir and find_system_dat(self.root_dir) else None
            p = filedialog.askopenfilename(title=t("选择 system.dat"), initialdir=init, filetypes=[("system.dat", "system.dat"), (t("所有文件"), "*.*")], parent=win)
            if p: path.set(p); refresh()
        ttk.Button(f0, text=t("浏览…"), command=browse).pack(side="left", padx=(6, 0))
        if self.root_dir and find_system_dat(self.root_dir): path.set(find_system_dat(self.root_dir))
        info.pack(padx=12, pady=6, anchor="w")
        f1 = ttk.Frame(win); f1.pack(fill="x", padx=12, pady=4)
        ttk.Label(f1, text=t("目标 HD Key:")).pack(side="left")
        cb = ttk.Combobox(f1, values=list(self.keys) + [t("自定义…")], state="readonly", width=18); cb.pack(side="left", padx=6); cb.current(0)
        hexv = tk.StringVar(); ent = ttk.Entry(win, textvariable=hexv); ent.pack(fill="x", padx=12)
        def on_pick(*_):
            n = cb.get()
            if n in self.keys: hexv.set(self.keys[n].hex().upper()); ent.state(["readonly"])
            else: hexv.set(""); ent.state(["!readonly"]); ent.focus()
        cb.bind("<<ComboboxSelected>>", on_pick); on_pick(); refresh()
        ttk.Label(win, text=t("可在 hd_keys.json 里增删常用 HD Key。"), foreground="#666").pack(padx=12, pady=4, anchor="w")
        def go(*_):
            try: key = parse_hd_key(hexv.get())
            except ValueError as ex: messagebox.showwarning(t("重签"), str(ex), parent=win); return
            if not path.get().strip(): messagebox.showwarning(t("重签"), t("请先选择 system.dat。"), parent=win); return
            tag = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", cb.get() if cb.get() in self.keys else "custom")
            out = os.path.join(APP_DIR, "resigned", "%s_%s" % (tag, time.strftime("%Y%m%d_%H%M%S")), "TDATA", "5443000d", "system.dat")
            try: ok, msg = resign_system_dat(path.get().strip(), key, out)
            except Exception as ex: messagebox.showerror(t("重签失败"), str(ex), parent=win); return
            win.destroy()
            if ok: messagebox.showinfo(t("重签完成"), t("已重签，输出（拷到目标主机的 TDATA\\5443000d）:\n") + out)
            else: messagebox.showerror(t("重签失败"), msg)
        ttk.Button(win, text=t("开始重签"), command=go).pack(pady=10)

    def sysupdate_dialog(self, mode="slot"):
        """Edit the TDATA system.dat play-time table / list order (see ngb_system_dat.py, docs/system-dat-research.md)."""
        import ngb_system_dat as SD
        self.keys = load_keys()
        win = tk.Toplevel(self); win.title(t("更新 system.dat（读档列表的游玩时间 / 顺序）")); win.geometry("800x700"); win.transient(self); win.grab_set()
        ttk.Label(win, text=t("底本必须是从 xemu / 360 当前拷出来的 system.dat（总时间、解锁、设置会原样保留）。原文件不会被修改，结果写到 resigned/<key>_<时间>/TDATA/5443000d/system.dat。"), wraplength=760).pack(padx=12, pady=(10, 4), anchor="w")
        base = tk.StringVar(value=(find_system_dat(self.root_dir) or "") if self.root_dir else "")
        f0 = ttk.Frame(win); f0.pack(fill="x", padx=12, pady=2)
        ttk.Label(f0, text=t("底本 system.dat:")).pack(side="left")
        ttk.Entry(f0, textvariable=base).pack(side="left", fill="x", expand=True, padx=6)
        def browse_base():
            p = filedialog.askopenfilename(title=t("选择 system.dat"), filetypes=[("system.dat", "system.dat"), (t("所有文件"), "*.*")], parent=win)
            if p: base.set(p)
        ttk.Button(f0, text=t("浏览…"), command=browse_base).pack(side="left")
        mv = tk.StringVar(value=mode)
        src = tk.StringVar(); src_lbl = tk.StringVar()
        f1 = ttk.Frame(win); f1.pack(fill="x", padx=12, pady=(6, 0))
        for text, val in ((t("更新单个档位（选一个存档文件夹）"), "slot"), (t("按整套 UDATA 同步（存在的写真实帧数，不存在的写 0）"), "sync"), (t("重置顺序（count=30，0..29）"), "order")):
            ttk.Radiobutton(f1, text=text, variable=mv, value=val, command=lambda: on_mode()).pack(anchor="w")
        f2 = ttk.Frame(win); f2.pack(fill="x", padx=12, pady=4)
        ttk.Label(f2, textvariable=src_lbl).pack(side="left")
        ent = ttk.Entry(f2, textvariable=src); ent.pack(side="left", fill="x", expand=True, padx=6)
        def browse_src():
            p = filedialog.askdirectory(title=t("选择文件夹"), parent=win)
            if p: src.set(p)
        bsrc = ttk.Button(f2, text=t("浏览…"), command=browse_src); bsrc.pack(side="left")
        def on_mode():
            m = mv.get()
            if m == "slot":
                r = self.current(); src_lbl.set(t("存档文件夹:")); src.set(r["path"] if r else "")
            elif m == "sync": src_lbl.set(t("5443000d 文件夹:")); src.set(self.root_dir or "")
            else: src_lbl.set(""); src.set("")
            st = "normal" if m != "order" else "disabled"; ent.config(state=st); bsrc.config(state=st)
        on_mode()
        f3 = ttk.Frame(win); f3.pack(fill="x", padx=12, pady=4)
        ttk.Label(f3, text=t("目标 HD Key:")).pack(side="left")
        cb = ttk.Combobox(f3, values=list(self.keys) + [t("自定义…")], state="readonly", width=18); cb.pack(side="left", padx=6); cb.current(0)
        hexv = tk.StringVar(); khex = ttk.Entry(win, textvariable=hexv); khex.pack(fill="x", padx=12)
        def on_pick(*_):
            n = cb.get()
            if n in self.keys: hexv.set(self.keys[n].hex().upper()); khex.state(["readonly"])
            else: hexv.set(""); khex.state(["!readonly"]); khex.focus()
        cb.bind("<<ComboboxSelected>>", on_pick); on_pick()
        out = tk.Text(win, wrap="none", height=22, font=("Consolas", 9)); out.pack(fill="both", expand=True, padx=12, pady=6)
        def show(text):
            out.config(state="normal"); out.delete("1.0", "end"); out.insert("1.0", text); out.config(state="disabled")
        show(t("点“预览”查看修改前后对比（不写文件）；点“写出”生成新的 system.dat。"))
        def busy(on): win.config(cursor="watch" if on else ""); win.update_idletasks()
        def args():
            m = mv.get(); s = src.get().strip()
            if not base.get().strip(): raise ValueError(t("请先选择底本 system.dat。"))
            if m != "order" and not s: raise ValueError(t("请先选择%s。") % (t("存档文件夹") if m == "slot" else t("5443000d 文件夹")))
            return m, base.get().strip(), (s or None)
        def preview():
            try:
                m, b, s = args(); busy(True)
                _, _, notes, report = SD.plan(m, b, s)
                show(report + "\n\n" + "\n".join(notes))
            except Exception as ex: show(t("出错: %s") % ex)
            finally: busy(False)
        def go():
            try:
                key = parse_hd_key(hexv.get()); m, b, s = args(); busy(True)
                res = SD.apply(m, b, s, key, cb.get() if cb.get() in self.keys else "custom")
            except Exception as ex: busy(False); show(t("出错: %s") % ex); messagebox.showerror(t("system.dat 更新失败"), str(ex), parent=win); return
            busy(False)
            show(res["report"] + "\n\n" + "\n".join(res["notes"]) + t("\n\n已写出并校验通过（重新解码一致、签名正确、其余字节未变）:\n") + res["out"])
            messagebox.showinfo(t("system.dat 已更新"), t("输出（拷到目标主机的 TDATA\\5443000d）:\n") + res["out"], parent=win)
        fb = ttk.Frame(win); fb.pack(pady=(0, 10))
        ttk.Button(fb, text=t("预览"), command=preview).pack(side="left", padx=6)
        ttk.Button(fb, text=t("写出"), command=go).pack(side="left", padx=6)

    def on_double(self, e):
        if self.tree.identify_region(e.x, e.y) != "cell": return      # header / blank area: do nothing
        self.open_folder()

    def delete_selected(self, *_):
        sl = self.selected()
        if not sl: messagebox.showinfo(t("删除"), t("请先选中存档（可 Ctrl/Shift 多选，或点“全选”）。")); return
        lst = ", ".join(str(r.get("slot", r["folder"])) for r in sl)
        if not messagebox.askyesno(t("删除"), t("确定永久删除选中的 %d 个存档文件夹吗？\n槽位: %s\n\n此操作不可撤销，建议先“复制所选存档到…”备份。") % (len(sl), lst), icon="warning", default="no"): return
        failed = []
        for r in sl:
            try:
                shutil.rmtree(r["path"]); self.notes.pop(r["folder"], None)
            except Exception as ex: failed.append("%s (%s)" % (r["folder"], ex))
        save_json(NOTES_FILE, self.notes); self.reload()
        if failed: messagebox.showerror(t("删除失败"), "\n".join(failed))
        return "break"

    def open_folder(self, *_):
        r = self.current()
        if not r: messagebox.showinfo(t("打开文件夹"), t("请先在列表里选中一个存档。")); return
        path = os.path.normpath(os.path.abspath(r["path"]))
        try:
            if sys.platform.startswith("win"): os.startfile(path)           # opens the single save's own folder
            elif sys.platform == "darwin": os.system('open "%s"' % path)
            else: os.system('xdg-open "%s" >/dev/null 2>&1 &' % path)
        except Exception as ex:
            messagebox.showerror(t("打开失败"), "%s\n%s" % (path, ex))


    def copy_dialog(self):
        sl = self.selected()
        if not sl: messagebox.showinfo(t("复制"), t("请先选中存档（可 Ctrl/Shift 多选，或点“全选”）。")); return
        dest = filedialog.askdirectory(title=t("选择复制到哪个文件夹（会在里面放入 %d 个存档文件夹）") % len(sl))
        if not dest: return
        title = messagebox.askyesno(t("复制"), t("同时复制标题文件（TitleMeta/TitleImage/SaveImage），并按 UDATA 结构放进名为 %s 的子文件夹吗？\n\n是 = 目标里新建 %s 子文件夹\n否 = 只把 %d 个存档文件夹直接放进所选文件夹") % (os.path.basename(self.root_dir), os.path.basename(self.root_dir), len(sl)))
        try: base, res = copy_saves(self.root_dir, [r["folder"] for r in sl], dest, title)
        except Exception as ex: messagebox.showerror(t("复制失败"), str(ex)); return
        bad = [x for x in res if not x[1]]
        messagebox.showinfo(t("复制完成"), t("已复制 %d / %d 个存档（按槽位顺序，修改时间依次递增）。\n目标: %s%s") % (len(res) - len(bad), len(res), base, (t("\n\n跳过: ") + ", ".join("%s(%s)" % (x[0], x[2]) for x in bad)) if bad else ""))

    def copy_clip(self):
        sl = self.selected()
        if not sl: messagebox.showinfo(t("复制"), t("请先选中存档（可 Ctrl/Shift 多选，或点“全选”）。")); return
        paths = [os.path.normpath(os.path.abspath(r["path"])) for r in sl]
        if not sys.platform.startswith("win"):
            self.copy_text("\n".join(paths)); messagebox.showinfo(t("复制"), t("非 Windows 系统，已把 %d 个路径复制成文本。") % len(paths)); return
        try: set_clipboard_files(paths)
        except Exception as ex: messagebox.showerror(t("复制失败"), str(ex)); return
        messagebox.showinfo(t("已复制到剪贴板"), t("已复制 %d 个存档文件夹。\n在资源管理器目标位置按 Ctrl+V 粘贴即可。") % len(paths))

    def copy_text(self, text):
        self.clipboard_clear(); self.clipboard_append(text)

    def popup(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid: return
        if iid not in self.tree.selection(): self.tree.selection_set(iid)
        r = self.current(); m = tk.Menu(self, tearoff=0)
        n = len(self.selected())
        m.add_command(label=t("打开存档文件夹（%s）") % r["folder"], command=self.open_folder)
        m.add_command(label=t("复制完整路径"), command=lambda: self.copy_text(os.path.normpath(os.path.abspath(r["path"]))))
        m.add_command(label=t("复制文件夹名"), command=lambda: self.copy_text(r["folder"]))
        m.add_command(label=t("复制所选存档到…（%d 个）") % n, command=self.copy_dialog)
        m.add_command(label=t("复制所选到剪贴板（%d 个）") % n, command=self.copy_clip)
        m.add_separator()
        m.add_command(label=t("编辑备注"), command=self.edit_note)
        m.add_command(label=t("移动到槽位…"), command=self.move_dialog)
        m.add_command(label=t("HD Key 重签…"), command=self.resign_dialog)
        m.add_separator()
        m.add_command(label=t("删除所选存档（%d 个）") % n, command=self.delete_selected)
        m.tk_popup(e.x_root, e.y_root)

    def export_csv(self):
        if not self.rows: return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="ngb_saves.csv")
        if not p: return
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow([t(c[1]) for c in COLUMNS])
            for r in sorted(self.rows, key=lambda r: r.get("slot", 9999)): w.writerow([self.cell(r, c[0]) for c in COLUMNS])
        messagebox.showinfo(t("已导出"), p)

if __name__ == "__main__":
    sys.modules.setdefault("ngb_save_manager", sys.modules["__main__"])    # ngb_system_dat imports this file: reuse it instead of loading a second copy
    if "--selftest" in sys.argv:       # headless check, no window
        root = find_save_root(sys.argv[sys.argv.index("--selftest") + 1])
        rows = [inspect(os.path.join(root, e)) for e in sorted(os.listdir(root)) if os.path.isdir(os.path.join(root, e))]
        print(len(rows), "saves;", sum(1 for r in rows if r and r["hash_ok"]), "hash ok;", sum(1 for r in rows if r and r.get("decrypt_ok")), "decrypted")
    else:
        App().mainloop()
