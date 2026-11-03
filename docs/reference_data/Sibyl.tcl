# vmd_molecule_cpk_element_only_strong.tcl
# Purpose:
#   Modify ONLY the molecular-structure representation(s), keeping ESP/isosurface/volume reps unchanged.
#   Default target is rep 0. Change target_reps if your molecular representation is another row.
#
# Usage in VMD Tk Console:
#   source vmd_molecule_cpk_element_only_strong.tcl

# ---------------- User settings ----------------
set target_reps {0}
set use_name_fallback 1
# ------------------------------------------------

# Get top molecule
if {[llength [molinfo list]] == 0} {
    puts "No molecule is loaded."
    return
}
set molid [molinfo top]

# ---------- Custom color table ----------
# RGB values are in the range 0.0 - 1.0
color change rgb 101 0.8000 0.8000 0.8000
color change rgb 102 0.8471 1.0000 1.0000
color change rgb 103 0.8000 0.4863 1.0000
color change rgb 104 0.8000 1.0000 0.0000
color change rgb 105 1.0000 0.7098 0.7098
color change rgb 106 0.5569 0.5569 0.5569
color change rgb 107 0.0980 0.0980 0.8980
color change rgb 108 0.8980 0.0000 0.0000
color change rgb 109 0.6980 1.0000 1.0000
color change rgb 110 0.6863 0.8863 0.9569
color change rgb 111 0.6667 0.3569 0.9490
color change rgb 112 0.6980 0.8000 0.0000
color change rgb 113 0.8196 0.6471 0.6471
color change rgb 114 0.4980 0.6000 0.6000
color change rgb 115 1.0000 0.4980 0.0000
color change rgb 116 1.0000 0.7765 0.1569
color change rgb 117 0.0980 0.9373 0.0980
color change rgb 118 0.4980 0.8196 0.8863
color change rgb 119 0.5569 0.2471 0.8275
color change rgb 120 0.6000 0.6000 0.0000
color change rgb 121 0.8980 0.8980 0.8863
color change rgb 122 0.7490 0.7569 0.7765
color change rgb 123 0.6471 0.6471 0.6667
color change rgb 124 0.5373 0.6000 0.7765
color change rgb 125 0.6078 0.4784 0.7765
color change rgb 126 0.4980 0.4784 0.7765
color change rgb 127 0.3569 0.4275 1.0000
color change rgb 128 0.3569 0.4784 0.7569
color change rgb 129 1.0000 0.4784 0.3765
color change rgb 130 0.4863 0.4980 0.6863
color change rgb 131 0.7569 0.5569 0.5569
color change rgb 132 0.4000 0.5569 0.5569
color change rgb 133 0.7373 0.4980 0.8863
color change rgb 134 1.0000 0.6275 0.0000
color change rgb 135 0.6471 0.1294 0.1294
color change rgb 136 0.3569 0.7294 0.8196
color change rgb 137 0.4392 0.1765 0.6863
color change rgb 138 0.4980 0.4000 0.0000
color change rgb 139 0.5765 0.9882 1.0000
color change rgb 140 0.5765 0.8784 0.8784
color change rgb 141 0.4471 0.7569 0.7882
color change rgb 142 0.3294 0.7098 0.7098
color change rgb 143 0.2275 0.6196 0.6588
color change rgb 144 0.1373 0.5569 0.5882
color change rgb 145 0.0392 0.4863 0.5490
color change rgb 146 0.0000 0.4078 0.5176
color change rgb 147 0.6000 0.7765 1.0000
color change rgb 148 1.0000 0.8471 0.5569
color change rgb 149 0.6471 0.4588 0.4471
color change rgb 150 0.4000 0.4980 0.4980
color change rgb 151 0.6196 0.3882 0.7098
color change rgb 152 0.8275 0.4784 0.0000
color change rgb 153 0.5765 0.0000 0.5765
color change rgb 154 0.2588 0.6196 0.6863
color change rgb 155 0.3373 0.0863 0.5569
color change rgb 156 0.4000 0.2000 0.0000
color change rgb 157 0.4392 0.8667 1.0000
color change rgb 158 1.0000 1.0000 0.7765
color change rgb 159 0.8471 1.0000 0.7765
color change rgb 160 0.7765 1.0000 0.7765
color change rgb 161 0.6392 1.0000 0.7765
color change rgb 162 0.5569 1.0000 0.7765
color change rgb 163 0.3765 1.0000 0.7765
color change rgb 164 0.2667 1.0000 0.7765
color change rgb 165 0.1882 1.0000 0.7765
color change rgb 166 0.1176 1.0000 0.7098
color change rgb 167 0.0000 1.0000 0.7098
color change rgb 168 0.0000 0.8980 0.4588
color change rgb 169 0.0000 0.8275 0.3176
color change rgb 170 0.0000 0.7490 0.2196
color change rgb 171 0.0000 0.6667 0.1373
color change rgb 172 0.2980 0.7569 1.0000
color change rgb 173 0.2980 0.6471 1.0000
color change rgb 174 0.1490 0.5765 0.8392
color change rgb 175 0.1490 0.4863 0.6667
color change rgb 176 0.1490 0.4000 0.5882
color change rgb 177 0.0863 0.3294 0.5294
color change rgb 178 0.0863 0.3569 0.5569
color change rgb 179 1.0000 0.8196 0.1373
color change rgb 180 0.7098 0.7098 0.7569
color change rgb 181 0.6471 0.3294 0.2980
color change rgb 182 0.3373 0.3490 0.3765
color change rgb 183 0.6196 0.3098 0.7098
color change rgb 184 0.6667 0.3569 0.0000
color change rgb 185 0.4588 0.3098 0.2667
color change rgb 186 0.2588 0.5098 0.5882
color change rgb 187 0.2588 0.0000 0.4000
color change rgb 188 0.2980 0.0980 0.0000
color change rgb 189 0.4392 0.6667 0.9765
color change rgb 190 0.0000 0.7294 1.0000
color change rgb 191 0.0000 0.6275 1.0000
color change rgb 192 0.0000 0.5569 1.0000
color change rgb 193 0.0000 0.4980 0.9490
color change rgb 194 0.0000 0.4196 0.9490
color change rgb 195 0.3294 0.3569 0.9490
color change rgb 196 0.4667 0.3569 0.8863
color change rgb 197 0.5373 0.3686 0.8863
color change rgb 198 0.6275 0.2078 0.8275
color change rgb 199 0.6588 0.1686 0.7765
color change rgb 200 0.6980 0.1176 0.7294
color change rgb 201 0.6980 0.0471 0.6471
color change rgb 202 0.7373 0.0471 0.5294
color change rgb 203 0.7765 0.0000 0.4000
color change rgb 204 1.0000 0.4980 0.4980
color change rgb 205 0.8980 0.4000 0.4000
color change rgb 206 0.8000 0.2980 0.2980
color change rgb 207 0.6980 0.2000 0.2000
color change rgb 208 0.6000 0.0980 0.0980
color change rgb 209 0.5490 0.0000 0.0000
color change rgb 210 0.4980 0.0000 0.0000
color change rgb 211 0.4471 0.0000 0.0000

# Element -> ColorID mapping
set elem_color_list {
    H 101 He 102 Li 103 Be 104 B 105 C 106 N 107 O 108 F 109 Ne 110
    Na 111 Mg 112 Al 113 Si 114 P 115 S 116 Cl 117 Ar 118 K 119 Ca 120
    Sc 121 Ti 122 V 123 Cr 124 Mn 125 Fe 126 Co 127 Ni 128 Cu 129 Zn 130
    Ga 131 Ge 132 As 133 Se 134 Br 135 Kr 136 Rb 137 Sr 138 Y 139 Zr 140
    Nb 141 Mo 142 Tc 143 Ru 144 Rh 145 Pd 146 Ag 147 Cd 148 In 149 Sn 150
    Sb 151 Te 152 I 153 Xe 154 Cs 155 Ba 156 La 157 Ce 158 Pr 159 Nd 160
    Pm 161 Sm 162 Eu 163 Gd 164 Tb 165 Dy 166 Ho 167 Er 168 Tm 169 Yb 170
    Lu 171 Hf 172 Ta 173 W 174 Re 175 Os 176 Ir 177 Pt 178 Au 179 Hg 180
    Tl 181 Pb 182 Bi 183 Po 184 At 185 Rn 186 Fr 187 Ra 188 Ac 189 Th 190
    Pa 191 U 192 Np 193 Pu 194 Am 195 Cm 196 Bk 197 Cf 198 Es 199 Fm 200
    Md 201 No 202 Lr 203 Rf 204 Db 205 Sg 206 Bh 207 Hs 208 Mt 209 Ds 210 Rg 211
}

foreach {el cid} $elem_color_list {
    catch {color Element $el $cid}

    # Fallback for files where VMD stores element symbols as atom names instead of element fields.
    # This is common for POSCAR/CONTCAR/CUBE-related workflows.
    if {$use_name_fallback} {
        catch {color Name $el $cid}
    }
}

# Check whether the current molecule has valid element labels
set sel [atomselect $molid "all"]
set elems [lsort -unique [$sel get element]]
set names [lsort -unique [$sel get name]]
$sel delete

set use_element 1
if {$use_name_fallback} {
    # If element labels are missing, empty, or mostly unknown, use Name coloring instead.
    if {[llength $elems] == 0 || ([llength $elems] == 1 && ([lindex $elems 0] eq "" || [lindex $elems 0] eq "X"))} {
        set use_element 0
    }
}

# Apply only to selected molecular representation(s)
set nreps [molinfo $molid get numreps]
foreach rep $target_reps {
    if {$rep < $nreps} {
        mol modstyle    $rep $molid CPK 0.7 0.3 12.0 12.0
        if {$use_element} {
            mol modcolor $rep $molid Element
            puts "Rep $rep: style = CPK 0.7 0.3 12.0 12.0, color = Element, material = Opaque"
        } else {
            mol modcolor $rep $molid Name
            puts "Rep $rep: style = CPK 0.7 0.3 12.0 12.0, color = Name fallback, material = Opaque"
            puts "Reason: VMD did not find valid element labels. Atom names will be used for coloring."
        }
        mol modmaterial $rep $molid Opaque
    } else {
        puts "Warning: rep $rep does not exist in molecule $molid."
    }
}

# Force display update
display update
