#!/usr/bin/env python3
# import sys
import os
import re
import subprocess
import json
import argparse
import shutil
from snakemake.utils import read_job_properties


class SbatchScheduler:
    '''
    Builds sbatch command. Commands map to SLURM sbatch options.
    Params:
    ------
    account         - -A/--account
    dependency      - {{dependencies}}
    error           - -e/--error
    mail_type       - --mail-type
    mail_user       - --mail-user
    ntasks          - -n/--ntasks
    output          - -o/--output
    qos             - -q/--qos
    time            - -t/--time
    '''

    def __init__(self):
        self.account = None
        self.dependency = None
        self.error = None
        self.mail_type = None
        self.mail_user = None
        self.ntasks = None
        self.output = None
        self.qos = None
        self.script = None
        self.time = None

    def build_cmd(self):
        ''' builds sbatch command matching its options '''
        sbatch_options = list()

        job_attributes = [
            'account', 'dependency', 'error', 'output', 'mail_type',
            'mail_user', 'ntasks', 'qos', 'time'
        ]

        for attribute in job_attributes:
            if getattr(self, attribute):
                attribute_value = getattr(self, attribute)
                sbatch_options.append('--{} \"{}\"'.format(
                    attribute.replace("_", "-"), attribute_value))

        sbatch_options.append(self.script)

        return 'sbatch' + ' ' + ' '.join(sbatch_options)


class QsubScheduler:
    """docstring for QsubScheduler"""

    def __init__(self):
        self.account = None
        self.dependency = None
        self.error = None
        self.resources = None
        self.mail_type = None
        self.mail_user = None
        self.ntasks = None
        self.output = None
        self.qos = None
        self.script = None
        self.time = None

    def build_cmd(self):

        resource_params = ""
        depend = ""
        qsub_options = list()

        # Exclusive node
        resource_params += " -l excl=1 "
        #        if self.time:
        #            resource_params += " -l \"walltime={}\" ".format(str(self.time))

        if self.ntasks:
            #            resource_params += "nodes=1:ppn={}\" ".format(str(self.ntasks))
            resource_params += " -pe mpi {} ".format(str(self.ntasks))

        if self.account:
            #            qsub_options.append(" -A " + str(self.account))
            qsub_options.append(" -q " + str(self.account))

        if self.error:
            qsub_options.append(" -e " + str(self.error))

        if self.output:
            qsub_options.append(" -o " + str(self.output))

        if self.mail_type:
            #            qsub_options.append(" -m " + str(self.mail_type))
            qsub_options.append(" -m s ")  # + str(self.mail_type))

        if self.mail_user:
            qsub_options.append(" -M " + str(self.mail_user))

        if self.qos:
            qsub_options.append(" -p " + str(self.qos))

        if resource_params:
            qsub_options.append(resource_params)

        if self.dependency:
            for jobid in self.dependency:
                depend = depend + ":" + jobid
            #qsub_options.append(" -W \"depend=afterok" + str(depend) + "\"")
            qsub_options.append(" -hold_jid " + ",".join(self.dependency))

        if self.script:
            qsub_options.append(" {} ".format(self.script))

        return "qsub -V -S /bin/bash " + " ".join(qsub_options)


def read_sample_config(input_json):
    ''' load input sample_config file. Output of balsamic config sample. '''

    try:
        with open(input_json) as f:
            return json.load(f)
    except Exception as e:
        raise e


def write_sacct_file(sacct_file, job_id):
    ''' writes a yaml file with job ids '''
    try:
        with open(sacct_file, 'a') as f:
            f.write(job_id + "\n")
    except FileNotFoundError as e:
        raise e


# def write_scheduler_dump(scheduler_file, cmd):
#    ''' writes sbatch dump for debuging purpose '''
#    try:
#        with open(scheduler_file, 'a') as f:
#            f.write(cmd + "\n")
#            f.write(sys.executable + "\n")
#    except OSError:
#        raise


def submit_job(sbatch_cmd, profile):
    ''' subprocess call for sbatch command '''
    # run sbatch cmd
    try:
        res = subprocess.run(sbatch_cmd,
                             check=True,
                             shell=True,
                             stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise e

    # Get jobid
    res = res.stdout.decode()

    if profile == "slurm":
        m = re.search("Submitted batch job (\d+)", res)
        jobid = m.group(1)
    elif profile == "qsub":
        jobid_tmp = str(res).split()[3]
        jobid = jobid_tmp.strip("\"()\"")

    print(jobid)
    return jobid


# def singularity_param(sample_config, script_dir, jobscript, sbatch_script):
#    ''' write a modified sbatch script based on singularity parameters '''
#    if 'bind_path' not in sample_config['singularity']:
#        raise KeyError("bind_path was not found in sample config.")

#    if 'main_env' not in sample_config['singularity']:
#        raise KeyError("main_env was not found in sample config.")

#    if 'container_path' not in sample_config['singularity']:
#        raise KeyError("container_path was not found sample config.")

#    try:
#        bind_path = sample_config['singularity']['bind_path']
#        main_env = sample_config['singularity']['main_env']
#        container_path = sample_config['singularity']['container_path']
#        with open(sbatch_script, 'a') as f:
#            f.write("#!/bin/bash" + "\n")
#            f.write(
#                f"function balsamic-run {{ singularity exec -B {bind_path} --app {main_env} {container_path} $@; }}"
#                + "\n")
#            f.write(f"# Snakemake original script {jobscript}" + "\n")
#            f.write(f"balsamic-run bash {jobscript}" + "\n")
#        sbatch_file = os.path.join(
#            script_dir, sample_config["analysis"]["case_id"] + ".sbatch")
#        return sbatch_file
#    except OSError:
#        raise


def get_parser():
    ''' argument parser '''
    parser = argparse.ArgumentParser(description='''
        This is an internal script and should be invoked independently.
        This script gets a list of arugments (see --help) and submits a job to slurm as
        afterok dependency.
        ''')
    parser.add_argument("dependencies",
                        nargs="*",
                        help="{{dependencies}} from snakemake")
    parser.add_argument("snakescript", help="Snakemake script")
    parser.add_argument("--sample-config",
                        help='balsamic config sample output')
    parser.add_argument("--profile", help="profile to run jobs")
    parser.add_argument("--account",
                        required=True,
                        help='cluster account name')
    parser.add_argument("--qos",
                        default='low',
                        help='cluster job Priority (slurm - QOS)')
    parser.add_argument("--mail-type", help='cluster mail type')
    parser.add_argument("--mail-user", help='mail user')
    parser.add_argument("--log-dir", help="Log directory")
    parser.add_argument("--result-dir", help="Result directory")
    parser.add_argument("--script-dir", help="Script directory")

    return parser


def main(args=None):
    ''' entry point for scheduler.py '''
    parser = get_parser()
    args = parser.parse_args(args)

    jobscript = args.snakescript
    job_properties = read_job_properties(jobscript)
    shutil.copy2(jobscript, args.script_dir)
    jobscript = os.path.join(args.script_dir, os.path.basename(jobscript))

    if args.profile == 'slurm':
        jobid = '%j'
        scheduler_cmd = SbatchScheduler()
        if args.dependencies:
            scheduler_cmd.dependency = ','.join(
                ["afterok:%s" % d for d in args.dependencies])
    elif args.profile == 'qsub':
        jobid = '${JOB_ID}'
        scheduler_cmd = QsubScheduler()
        scheduler_cmd.dependency = args.dependencies

    if not args.mail_type:
        mail_type = job_properties["cluster"]["mail_type"]

    sample_config = read_sample_config(input_json=args.sample_config)

    sacct_file = os.path.join(args.log_dir,
                              sample_config["analysis"]["case_id"] + ".sacct")

    balsamic_run_mode = os.getenv("BALSAMIC_STATUS", "conda")
    #    if balsamic_run_mode == 'container' and 'singularity' in sample_config:
    #        sbatch_script = os.path.join(args.script_dir,
    #                                     "sbatch." + os.path.basename(jobscript))
    #        sbatch_file = singularity_param(sample_config=sample_config,
    #                                        script_dir=args.script_dir,
    #                                        jobscript=jobscript,
    #                                        sbatch_script=sbatch_script)
    #        jobscript = sbatch_script

    scheduler_cmd.account = args.account
    scheduler_cmd.mail_type = mail_type
    scheduler_cmd.error = os.path.join(
        args.log_dir,
        os.path.basename(jobscript) + "_" + jobid + ".err")
    scheduler_cmd.output = os.path.join(
        args.log_dir,
        os.path.basename(jobscript) + "_" + jobid + ".out")

    scheduler_cmd.ntasks = job_properties["cluster"]["n"]
    scheduler_cmd.time = job_properties["cluster"]["time"]
    scheduler_cmd.mail_user = args.mail_user
    scheduler_cmd.script = jobscript

    jobid = submit_job(scheduler_cmd.build_cmd(), args.profile)

    # scheduler_file = os.path.join(args.script_dir, sample_config["analysis"]["case_id"] + ".scheduler_dump")
    #    if balsamic_run_mode == 'container' and 'singularity' in sample_config:
    # write_scheduler_dump(scheduler_file=scheduler_file, cmd=scheduler_cmd.build_cmd())

    write_sacct_file(sacct_file=sacct_file, job_id=jobid)


if __name__ == '__main__':
    main()
