# vim: syntax=python tabstop=4 expandtab
# coding: utf-8

import os
import logging

from yapf.yapflib.yapf_api import FormatFile

from BALSAMIC.utils.cli import write_json
from BALSAMIC.utils.rule import get_rule_output
from BALSAMIC.utils.rule import get_result_dir
from BALSAMIC.utils.rule import get_vcf

shell.prefix("set -eo pipefail; ")

LOG = logging.getLogger(__name__)

# Set temporary dir environment variable
os.environ['TMPDIR'] = get_result_dir(config)

tmp_dir = os.path.join(get_result_dir(config), "tmp") 
rule_dir = config["rule_directory"]
benchmark_dir = config["analysis"]["benchmark"]
fastq_dir = get_result_dir(config) + "/fastq/"
bam_dir = get_result_dir(config) + "/bam/"
cnv_dir = get_result_dir(config) + "/cnv/"
cutadapt_dir = get_result_dir(config) + "/cutadapt/"
result_dir = get_result_dir(config) + "/"
qc_dir = get_result_dir(config) + "/qc/"
vcf_dir = get_result_dir(config) + "/vcf/"
vep_dir = get_result_dir(config) + "/vep/"

singularity_image = config['singularity']['image'] 

try:
    config["SENTIEON_LICENSE"] = os.environ["SENTIEON_LICENSE"]
    config["SENTIEON_INSTALL_DIR"] = os.environ["SENTIEON_INSTALL_DIR"]
except Exception as error:
    LOG.error("ERROR: Set SENTIEON_LICENSE and SENTIEON_INSTALL_DIR environment variable to run this pipeline.")
    raise

SENTIEON_DNASCOPE = rule_dir + 'assets/sentieon_models/SentieonDNAscopeModelBeta0.4a-201808.05.model'
SENTIEON_TNSCOPE = rule_dir + 'assets/sentieon_models/SentieonTNscopeModel_GiAB_HighAF_LowFP-201711.05.model'
os.environ["SENTIEON_TMPDIR"] = result_dir

# explictly check if cluster_config dict has zero keys.
if len(cluster_config.keys()) == 0:
    cluster_config = config

# rules for pipeline
quality_check = ["snakemake_rules/quality_control/fastp.rule", \
                 "snakemake_rules/sentieon/sentieon_qc_metrics.rule", \
                 "snakemake_rules/quality_control/picard_wgs.rule", \
                 "snakemake_rules/quality_control/multiqc.rule"]
preprocessing = ["snakemake_rules/sentieon/sentieon_alignment.rule"]

if config['analysis']['analysis_type'] == "paired":
    variant_calling = ["snakemake_rules/sentieon/sentieon_tn_varcall.rule", \
                       "snakemake_rules/sentieon/sentieon_germline.rule", \
                       "snakemake_rules/variant_calling/somatic_sv_tumor_normal.rule", \
                       "snakemake_rules/variant_calling/cnvkit_paired.rule"]
    somatic_caller = ['tnhaplotyper','tnsnv', 'tnscope', 'manta', 'cnvkit']
    germline_caller = ['dnascope']

else:
    variant_calling = ["snakemake_rules/sentieon/sentieon_t_varcall.rule", \
                       "snakemake_rules/sentieon/sentieon_germline.rule", \
                       "snakemake_rules/variant_calling/somatic_sv_tumor_only.rule", \
                       "snakemake_rules/variant_calling/cnvkit_single.rule"]
    somatic_caller = ['tnhaplotyper','tnsnv', 'tnscope', 'manta', 'cnvkit']
    germline_caller = ['dnascope']

annotation = ["snakemake_rules/annotation/vep.rule"]

pipeline = quality_check + preprocessing + variant_calling + annotation 


for rule in pipeline:
    include: os.path.join(rule_dir, rule)

if 'delivery' in config:
    wildcard_dict = { "sample": list(config["samples"].keys()),
                      "case_name": config["analysis"]["case_id"],
                      "var_type": ["CNV", "SNV", "SV"],
                      "var_class": ["somatic", "germline"],
                      "var_caller": somatic_caller + germline_caller,
                      "bedchrom": config["panel"]["chrom"] if "panel" in config else [], 
                      "allow_missing": True
                    }


    if 'rules_to_deliver' in config:
        rules_to_deliver = config['rules_to_deliver'].split(",")
    else:
        rules_to_deliver = ['multiqc']

    output_files_ready = [('path', 'path_index', 'step', 'tag', 'id', 'format')]
    for my_rule in set(rules_to_deliver):
        try:
            housekeeper_id = getattr(rules, my_rule).params.housekeeper_id
        except (ValueError, AttributeError, RuleException, WorkflowError) as e:
            LOG.warning("Cannot deliver step (rule) {}: {}".format(my_rule,e))
            continue

        LOG.info("Delivering step (rule) {}.".format(my_rule))
        output_files_ready.extend(get_rule_output(rules=rules, rule_name=my_rule, output_file_wildcards=wildcard_dict))

    output_files_ready = [dict(zip(output_files_ready[0], value)) for value in output_files_ready[1:]]
    delivery_ready = os.path.join(get_result_dir(config), "delivery_report", config["analysis"]["case_id"] + "_delivery_ready.hk" )
    write_json(output_files_ready, delivery_ready)
    FormatFile(delivery_ready) 
 

rule all:
    input:
        expand(bam_dir + "{sample}.bam", sample=config["samples"]),
        expand(bam_dir + "{sample}.dedup.bam", sample=config["samples"]),
        expand(bam_dir + "{sample}.dedup.realign.bam", sample=config["samples"]),
        expand(bam_dir + "{sample}.dedup.realign.recal_data.table", sample=config["samples"]),
        expand(bam_dir + "{sample}.dedup.realign.recal.csv", sample=config["samples"]),
        expand(bam_dir + "{sample}.dedup.realign.recal.pdf", sample=config["samples"]),
        expand(vep_dir + "{vcf}.{filters}.vcf.gz", vcf=get_vcf(config, somatic_caller, [config["analysis"]["case_id"]]), filters = ["all", "pass"]),
        expand(qc_dir + "{sample}_sentieon_wgs_metrics.txt", sample=config["samples"]),
        expand(qc_dir + "{sample}_coverage.gz", sample=config["samples"]),
        expand(qc_dir + "multiqc_report.html"),
    output:
        os.path.join(get_result_dir(config), "analysis_finish")
    shell:
        "date +'%Y-%m-%d T%T %:z' > {output}"

