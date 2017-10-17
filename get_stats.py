import Bio.pairwise2 as bio
import pandas as pd
import numpy as np
import matplotlib as mpl
mpl.use('Agg')  # required to use matplotlib without X (via ssh + screen)
import matplotlib.pyplot as plt
import sys

#######################################
## OPEN FILE

#INPUT_FILE = sys.argv[1]
#f = open(INPUT_FILE,"r")

# file should contain aligned sequences only with different alignments separated by an empty line
f = open("./all.alignments","r")

# alignments are of unique reads only, read in separately the number of each of these reads in the original (qc-filtered) FASTQ file 
cfile = open("all.readCounts_needleOrder","r")
all_readCounts = [int(readCount) for readCount in cfile.read().splitlines()]

#######################################
# READ IN ALIGNMENTS, STORE REF AND READ IN SEPERATE LISTS

next_ = [] # save read and ref sequences of the next alignment
all_reads = [] # save all read sequences in f, each element is one read stored as one string 
all_refs = [] # equivalent to all_reads but for ref sequences -> all_reads and all_refs are matched by index (all_reads[0] was aligned to all_refs[0]
all_files = [] # store the file name of each read's needle alignment


# loop over file to fill all_reads and all_refs
for line in f:
	if '.needle' in line:
		all_files.append(line.rstrip('\n'))
	else:	
		# append all sequences of the next alignment to next_
		next_.append(line.rstrip('\n'))
		# once the empty newline is encountered that separates distinct alignments, separate read and ref sequences of next_ and store as one string element of all_reads and all_refs respectively
		if(line == '\n' or line == ''):
			all_reads.append(''.join(next_[0:len(next_):2]))
			all_refs.append(''.join(next_[1:len(next_):2]))
			next_ = []
# readline() returns '' for file end, for-loop doesn't -> compensate by running this code once more (think of a better way later...)
all_reads.append(''.join(next_[0:len(next_):2]))
all_refs.append(''.join(next_[1:len(next_):2]))

# close the file!
f.close()

# make sure there is a 1:1 matching between these files -> must all have the same length!
#print(len(all_reads))
#print(len(all_refs))
#print(len(all_readCounts))
assert(len(all_reads) == len(all_refs))
assert(len(all_reads) == len(all_readCounts))


#######################################
# EXTRACT INSERT SEQUENCE FROM READ


# check each alignment for insert/itd and save index in all_reads/all_refs/all_files to idx, insert/itd length to length and insert/itd start/stop position to start/end dicts based on insert/itd classification
w_ins = {"idx": []}
w_ins_single = {"idx": [], "length": [], "start": [], "end": []}
w_itd_exact = {"idx": [], "length": [], "start": [], "end": [], "tandem2_start": []}
w_itd_nonexact = {"idx": [], "length": [], "start": [], "end": [], "tandem2_start": []}
w_itd_nonexact_fail = {"idx": [], "length": [], "start": [], "end": []}

# test for one alignment, later loop over all:
for read,ref,i in zip(all_reads, all_refs, range(len(all_reads))):
	readn = np.array(list(read))
	refn = np.array(list(ref))
	refn_noGap = [base for base in refn if base != '-']

	# get indeces of inserts in read (positions where reference has a gap and read does not)
	insert_idxs = np.array(list(range(len(readn))))[np.bitwise_and(refn == '-', readn != '-')]
	
	# clean up inserts -> ignore single base insertions 
	shift_left = np.append(0, insert_idxs)[0:len(insert_idxs)]
	shift_right = np.append(insert_idxs, [0])[1:]
	insert_idxs = insert_idxs[np.bitwise_or((insert_idxs -shift_left == 1),(insert_idxs -shift_right == -1))]
	assert len(insert_idxs) != 1  # make sure insert length can never be 1 
	
	insert_length = len(insert_idxs)	
	# if there is an insert  --> require min length of insert and in-frame
	if(insert_length >= 6 and insert_length % 3 == 0):
		w_ins["idx"].append(i)
		insert_start = insert_idxs[0]
		insert_end = insert_idxs[-1]
	
		insert_start_ref = insert_end - sum(base == '-' for base in refn[0:insert_end])
		if insert_start == 0 or insert_end == len(refn)-1:
			insert_start_ref = insert_start_ref - insert_length
		# relative to the reference, get coord of the first WT base after insert	
		insert_end_ref = insert_start_ref +insert_length -1
		
		# if there is one insert only  --> later think about how to handle multiple inserts...   --> not sure if this is actually always working! (all_insertions_single included an alignment with multiple gaps!)
		if(insert_length == insert_end - insert_start +1):
			w_ins_single["idx"].append(i)
			w_ins_single["length"].append(insert_length)
			w_ins_single["start"].append(insert_start_ref)
			w_ins_single["end"].append(insert_end_ref)
				
			# check whether the insert is contained within non-insert read a second time -> that'd be an exact ITD, later think about how to handle non-exact matches or matches +/- a few bases
			readn_nonIns = np.delete(readn,insert_idxs)
			ins = readn[insert_idxs]

			################################
			# FIND INS IN REF --> THAT MAKES INS AN ITD

			# ITD COMES AFTER INS
			tandem2_after = ''.join(refn_noGap).find(''.join(ins).lower(), insert_start_ref,len(refn_noGap))

			# ITD COMES BEFORE INS
			tandem2_before = ''.join(reversed(refn_noGap)).find(''.join(reversed(ins)).lower(), len(refn_noGap) -1 -insert_end_ref  +insert_length -1, len(refn_noGap))
			
			# CONVERRT BEFORE-COORD (REV) BACK TO FORWARD COORD TO COMPARE TO AFTER-COORD
			tandem2_before_converted = len(refn_noGap) -1 -tandem2_before -insert_length +1

			# TEST WHETHER A SECOND COPY OF THE INS WAS FOUND
			# IF THERE ARE TWO COPIES, FIND THE ONE CLOSEST TO INS (mostly relevant for short ITDs whose sequence may be present multiple times within the REF)
			tandem2_start_ref = None
			if tandem2_after == -1 and tandem2_before == -1:
				tandem2_start_ref = -1 # not found --> no itd present
			elif tandem2_after != "-1":
				#tandem2_start_ref = insert_end_ref + tandem2_after
				tandem2_start_ref = tandem2_after
			elif tandem2_before != -1:
				#tandem2_start_ref = insert_start_ref - tandem2_before
				tandem2_start_ref = tandem2_before_converted
			elif tandem2_after < tandem2_before:
				#tandem2_start_ref = insert_end_ref + tandem2_after
				tandem2_start_ref = tandem2_after
			elif tandem2_before < tandem2_after:
				#tandem2_start_ref = insert_start_ref - tandem2_before
				tandem2_start_ref = tandem2_before_converted
			assert tandem2_start_ref is not None  # should be assigned something!

			tandem2_start = ''.join(readn_nonIns).find(''.join(ins)) # alignment coord  -> not the first instance!
			if(tandem2_start_ref != -1):   # ---> also check that index of second match is sufficiently close to insert! (for exact match and alignment approach!)
				w_itd_exact["idx"].append(i)
				w_itd_exact["length"].append(insert_length)
				w_itd_exact["start"].append(insert_start_ref)
				w_itd_exact["end"].append(insert_end_ref)
				w_itd_exact["tandem2_start"].append(tandem2_start_ref)
			else:
				# if there is no exact match, use local alignment to find ins in nonIns-read and check for sufficiently good alignment -> require 90% of bases mapped ->  +5 score per matching base
				max_score = len(ins) * 5
				min_score = max_score * 0.9
				# arguments: seq1, seq2, match-score, mismatch-score, gapopen-score, gapextend-score --> match/mismatch from needle default (/usr/share/EMBOSS/data/EDNAFULL), gap as passed to needle in my script
				# output: list of optimal alignments, each a list of seq1, seq2, score, start-idx, end-idx 
				alignment = bio.align.localms(''.join(ins), ''.join(readn_nonIns), 5, -4, -20, -0.05)[0]
				alignment_score, alignment_start, alignment_end = alignment[2:5]
				
				if(alignment_score >= min_score):
					w_itd_nonexact["idx"].append(i)
					w_itd_nonexact["length"].append(insert_length)
					w_itd_nonexact["start"].append(insert_start_ref)
					w_itd_nonexact["end"].append(insert_end_ref)
					w_itd_nonexact["tandem2_start"].append(alignment_start)
					#w_itd_nonexact["tandem2_start"].append(tandem2_start_ref)
				else:
					w_itd_nonexact_fail["idx"].append(i)
					w_itd_nonexact_fail["length"].append(insert_length)
					w_itd_nonexact_fail["start"].append(insert_start_ref)
					w_itd_nonexact_fail["end"].append(insert_end_ref)
					#print(bio.format_alignment(*alignment))

w_itd = {"idx": w_itd_exact["idx"] + w_itd_nonexact["idx"], "length": w_itd_exact["length"] + w_itd_nonexact["length"], "start": w_itd_exact["start"] + w_itd_nonexact["start"], "end": w_itd_exact["end"] + w_itd_nonexact["end"], "tandem2_start": w_itd_exact["tandem2_start"] + w_itd_nonexact["tandem2_start"]}
print("-----------------------------------")

########################################
# PLOT SEPARATE HISTOGRAMS FOR COUNTS OF INSERT/ITD LENGTH/START/STOP/START-STOP PER CATEGORY

def plot_hist(title_, xlab_, top=True, bottom=True):
	ax.bar(counts_table_value,counts_table, align='center', color="lightgrey")
	ax.ticklabel_format(style='sci', axis='y', scilimits=(0,0))
	# Hide the right and top spines
	ax.spines['right'].set_visible(False)
	ax.spines['top'].set_visible(False)
	# Only show ticks on the left and bottom spines
	ax.yaxis.set_ticks_position('left')
	# set axes limits
	axes = plt.gca()
	ax.tick_params(direction='out')
	axes.set_xlim([0,len(counts_table)])
	axes.set_ylim([0,1 * 10**i])
	# set axes labels and tick width
	ax.set_ylabel("Counts")
	ax.xaxis.set_major_locator(mpl.ticker.MultipleLocator(10))
	ax.yaxis.major.formatter._useMathText = True
	if(top):
		ax.set_title(title_)
	if(bottom):
		ax.xaxis.set_ticks_position('bottom')
		ax.set_xlabel(xlab_)
	else:
		plt.tick_params(axis='x',which='both',bottom='on',top='off',labelbottom='on') 
		# changes apply to the x-axis, both major and minor ticks are affected, ticks along the bottom edge are on, ticks along the top edge are off, labels along the bottom edge are on

df_itd = pd.DataFrame(w_itd)
df_itd["counts"] = np.zeros(len(df_itd))

for ins_type,ins_filename,title_ in zip([w_ins_single, w_itd_exact, w_itd_nonexact, w_itd, w_itd_nonexact_fail],["w_ins_single", "w_itd_exact", "w_itd_nonexact", "w_itd", "w_itd_nonexact_fail"],["Single insertions", "Single ITDs - exact matching", "Single ITDs - non-exact matching", "Single ITDs - all", "Single insertions - failed ITD matching"]):
	print(title_)
	for stat,xlab_ in zip(["length","start","end"], ["Insert length (bp)","Insert start position","Insert end position"]):
		print(xlab_)
		counts_table = None
		counts_table_value = None
		counts_table_value_toIndexOffset = 0
		if stat == "length":
			counts_table = np.zeros(max(ins_type[stat]) +1)
			counts_table_value = np.arange(0,len(counts_table))
		else:
			assert(stat == "start" or stat == "end")
			min_val = min(0,min(ins_type[stat]))
			max_val = max(ins_type[stat])
			counts_table = np.zeros(max_val + abs(min_val) + 1)
			counts_table_value = np.arange(min_val, max_val +1) 
			assert(len(counts_table) == len(counts_table_value))
			counts_table_value_toIndexOffset = abs(min_val)
		
		# sum up counts of insert/itds with the same lengths/statistic (length, start or stop)
		for i in range(len(ins_type[stat])):
			i_stat = ins_type[stat][i] + counts_table_value_toIndexOffset
			i_idx = ins_type["idx"][i]
			counts_table[i_stat] = counts_table[i_stat] + all_readCounts[i_idx]
			if((ins_filename=="w_itd_exact" or ins_filename=="w_itd_nonexact") and stat=="length"):
				df_itd.ix[df_itd["idx"] == i_idx, "counts"] = all_readCounts[i_idx]

		#print(counts_table)
		# PLOT
		fig = plt.figure(figsize=(8.27, 11.69)) #A4 DIN size
		n_plots = 5
		for i in range(1,n_plots+1):
			ax = fig.add_subplot(n_plots,1,n_plots -i +1)
			top_plt = False
			bottom_plt = False
			if(i == n_plots):
				top_plt = True
			if(i == 1):
				bottom_plt = True
			plot_hist(title_, xlab_, top_plt, bottom_plt)	
	
		fig.tight_layout() # required to not have subplots overlap
		# save counts as CSV table and as histogram 
		pd.DataFrame(counts_table, index=counts_table_value, columns=["counts"]).to_csv("table_" + stat + "_" + ins_filename + ".csv")
		plt.savefig("plot_" + stat + "_" + ins_filename + ".pdf")


########################################
# COLLECT AND SAVE TO FILE ALL ITDs DETECTED ALONG WITH LENGTH, START, STOP, TOTAL COUNTS AND INDICES AND COUNTS OF INDIVIDUAL UNIQUE READS

df_itd_grouped = df_itd.groupby(by=["length","start","end","tandem2_start"], as_index=False).sum()
df_itd_grouped["counts_each"] = np.zeros(len(df_itd_grouped))
df_itd_grouped[["idx","counts_each"]] = df_itd_grouped[["idx","counts_each"]].astype("object")

for i in range(len(df_itd_grouped)):
	this_itd = df_itd[np.array(df_itd["start"] == df_itd_grouped.ix[i,"start"]) * np.array(df_itd["end"] == df_itd_grouped.ix[i,"end"]) * np.array(df_itd["tandem2_start"] == df_itd_grouped.ix[i,"tandem2_start"])]
	
	df_itd_grouped.set_value(i,"idx",np.array(all_files)[this_itd["idx"]].tolist())
	df_itd_grouped.set_value(i,"counts_each",[np.int(x) for x in this_itd["counts"]])

df_itd_grouped.to_csv("flt3_itds.csv")



########################################
# PRINT FILENAMES OF EACH CATEGORY TO FILE
			
out = open("flt3_insertions.txt","w")
out.write("\n".join(np.array(all_files)[w_ins["idx"]]) + "\n")
out.close()

out = open("flt3_insertions_single.txt","w")
out.write("\n".join(np.array(all_files)[w_ins_single["idx"]]) + "\n")
out.close()

out = open("flt3_insertions_single_itd_exact.txt","w")
out.write("\n".join(np.array(all_files)[w_itd_exact["idx"]]) + "\n")
out.close()

out = open("flt3_insertions_single_itd_nonexact.txt","w")
out.write("\n".join(np.array(all_files)[w_itd_nonexact["idx"]]) + "\n")
out.close()

out = open("flt3_insertions_single_itd_nonexact_fail.txt","w")
out.write("\n".join(np.array(all_files)[w_itd_nonexact_fail["idx"]]) + "\n")
out.close()


########################################
# PRINT SUMMARY STATISTICS on the number of reads in each category

print("--------------------")
print("Unique reads supporting each type of insert -> NOT number of distinct inserts!")
print("Insertions: {}".format(len(w_ins["idx"])))
print("One insertion only: {}".format(len(w_ins_single["idx"])))
print("Single exact ITD: {}".format(len(w_itd_exact["idx"])))
print("Single non-exact ITD: {}".format(len(w_itd_nonexact["idx"])))
print("Single insertion failed alignment: {}".format(len(w_itd_nonexact_fail["idx"])))




