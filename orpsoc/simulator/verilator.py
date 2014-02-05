import os
import shutil
import subprocess
from orpsoc import utils
from .simulator import Simulator

class Source(Exception):
     def __init__(self, value):
         self.value = value
     def __str__(self):
         return repr(self.value)


class Verilator(Simulator):

    TOOL_NAME = 'VERILATOR'
    def __init__(self, system):
        self.cores = []

        super(Verilator, self).__init__(system)

        self.verilator_options = []
        self.src_files = []
        self.include_files = []
        self.include_dirs = []
        self.tb_toplevel = ""
        self.src_type = 'C'
        self.define_files = []


        if system.verilator is not None:
            self._load_dict(system.verilator)
        self.verilator_root = os.getenv('VERILATOR_ROOT')
        if not self.verilator_root:
            print("Environment variable VERILATOR_ROOT was not found. It should be set to the verilator install path")
            exit(1)
        self.sim_root = os.path.join(self.build_root, 'sim-verilator')

    def _load_dict(self, items):
        for item in items:
            if item == 'verilator_options':
                self.verilator_options = items.get(item).split()
            elif item == 'src_files':
                self.src_files = items.get(item).split()
            elif item == 'include_files':
                self.include_files = items.get(item).split()
                self.include_dirs  = list(set(map(os.path.dirname, self.include_files)))
            elif item == 'tb_toplevel':
                self.tb_toplevel = items.get(item)
            elif item == 'source_type':
                self.src_type = items.get(item)
            elif item == 'define_files':
                self.define_files = items.get(item).split()
            else:
                print("Warning: Unknown item '" + item +"' in verilator section")

    def export(self):
        src_dir = self.system.files_root
        dst_dir = self.sim_root
        src_files = list(self.src_files)
        src_files += self.include_files
        src_files += [self.tb_toplevel]
        dirs = list(set(map(os.path.dirname, src_files)))
        for d in dirs:
            if not os.path.exists(os.path.join(dst_dir, d)):
                os.makedirs(os.path.join(dst_dir, d))

        for f in src_files:
            if(os.path.exists(os.path.join(src_dir, f))):
                shutil.copyfile(os.path.join(src_dir, f), 
                                os.path.join(dst_dir, f))

    def configure(self):
        super(Verilator, self).configure()
        self.export()
        self._write_config_files()

    def _write_config_files(self):
        self.verilator_file = 'input.vc'
        f = open(os.path.join(self.sim_root,self.verilator_file),'w')

        for include_dir in self.verilog.include_dirs:
            f.write("+incdir+" + os.path.abspath(include_dir) + '\n')
        for src_file in self.verilog.src_files:
            f.write(os.path.abspath(src_file) + '\n')
        f.close()
        #convert verilog defines into C file
        for files in self.define_files:
            read_file = os.path.join(self.src_root,files)
            write_file = os.path.join(os.path.dirname(os.path.join(self.sim_root,self.tb_toplevel)),os.path.splitext(os.path.basename(files))[0]+'.h')
            utils.convert_V2H(read_file, write_file)

        
    def build(self):
        super(Verilator, self).build()
        if self.src_type == 'C':
            self.build_C()
        elif self.src_type == 'systemC':
            self.build_SysC()
        else:
            raise Source(self.src_type)


    def build_C(self):
        args = ['-c']
        args += ['-I'+s for s in self.include_dirs]
        for src_file in self.src_files:
            print("Compiling " + src_file)
            utils.launch('gcc',
                         args + [src_file],
                         cwd=self.sim_root)

        object_files = [os.path.splitext(os.path.basename(s))[0]+'.o' for s in self.src_files]

        cmd = os.path.join(self.verilator_root,'bin','verilator')

        args = [cmd]
        args += ['--cc']
        args += ['-f']
        args += [self.verilator_file]
        args += ['--top-module']
        args += ['orpsoc_top']
        args += ['--exe']
        args += [os.path.join(self.sim_root, s) for s in object_files]
        args += [self.tb_toplevel]
        args += self.verilator_options

        utils.launch('bash', args, cwd = os.path.join(self.sim_root), stderr = open(os.path.join(self.sim_root,'verilator.log'),'w'))

        utils.launch('make -f Vorpsoc_top.mk Vorpsoc_top',
                     cwd=os.path.join(self.sim_root, 'obj_dir'),
                     shell=True)

    def build_SysC(self):

        object_files = [os.path.splitext(os.path.basename(s))[0]+'.o' for s in self.src_files]

        #verilog
        cmd = os.path.join(self.verilator_root,'bin','verilator') 

        args = [cmd]
        args += ['--sc']
        args += ['--top-module']
        args += ['orpsoc_top']
        args += ['-f']
        args += [self.verilator_file]
        args += ['--exe']
        args += [os.path.join(self.sim_root, s) for s in object_files]
        args += [self.tb_toplevel]
        args += self.verilator_options

        utils.launch('bash', args, cwd = os.path.join(self.sim_root), stderr = open(os.path.join(self.sim_root,'verilator.log'),'w'))


         #src_files        
        args = ['-I.']
        args += ['-MMD']
        args += ['-I'+s for s in self.include_dirs]
        args += ['-Iobj_dir']
        args += ['-I'+os.path.join(self.verilator_root,'include')]
        args += ['-I'+os.path.join(self.verilator_root,'include', 'vltstd')]  
        args += ['-DVL_PRINTF=printf']
        args += ['-DVM_TRACE=1']
        args += ['-DVM_COVERAGE=0']
        args += ['-I'+os.getenv('SYSTEMC_INCLUDE')]
        args += ['-Wno-deprecated']
        args += [os.getenv('SYSTEMC_CXX_FLAGS')]
        args += ['-c']
        args += ['-g']

        for src_file in self.src_files:
            print("Compiling " + src_file)
            utils.launch('g++',args + ['-o' + os.path.splitext(os.path.basename(src_file))[0]+'.o']+ [src_file],
                                cwd=self.sim_root)

        #tb_toplevel
        utils.launch('make -f Vorpsoc_top.mk Vorpsoc_top',
                     cwd=os.path.join(self.sim_root, 'obj_dir'),
                     shell=True)
        
    def run(self, args):
        #TODO: Handle arguments parsing
        utils.launch('./Vorpsoc_top',
                     args,
                     cwd=os.path.join(self.sim_root, 'obj_dir'))
        
