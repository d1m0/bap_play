extern crate cretonne;
extern crate cton_reader;
extern crate docopt;
extern crate rustc_serialize;
extern crate z3;

use std::collections::HashMap;
use cretonne::ir::{Opcode, InstructionData, Type,
                   DataFlowGraph, Value, Inst};
use cretonne::ir::immediates::{Imm64, Offset32};
use self::z3::{Context, Ast, Sort};
use std::ops::DerefMut;
use std::iter::Iterator;
use std::borrow::Borrow;
use std::marker::PhantomData;
use std::fmt::Display;

fn to_z3_sort<'ctx>(ctx: &'ctx Context, typ: &Type) -> Sort<'ctx> {
    ctx.bitvector_sort(typ.bits() as u32)
}

#[derive(PartialEq, Eq, Hash, Copy, Clone)]
enum Z3SSAVal {
    CtonVal(Value),
    Memory(u64),
}

pub struct Z3State<'ctx> {
    ctx:    &'ctx Context,
    defs:   HashMap<Z3SSAVal, Ast<'ctx>>,
    sorts:  HashMap<Z3SSAVal, Sort<'ctx>>,
    def_order:   Vec<Z3SSAVal>,
    val_to_ssa_name:   HashMap<Z3SSAVal, String>,
    addr_bits:  u32,
    val_bits:   u32,
    mem_ssa_ctr:    u64,
}

#[derive(Copy, Clone, Debug)]
enum Z3UnOps {
    BVSignExt,
    BVZeroExt,
}

#[derive(Copy, Clone, Debug)]
enum Z3BinOps {
    BVAdd,
    BVSub,
    BVMul,
    BVUdiv,
    BVSdiv,
    BVUrem,
    BVSrem,
    BVAnd,
    BVOr,
    BVXor,
    BVShl,
    BVLshr,
    BVAshr,
}

macro_rules! ASSERT_SINGLE_RESULT {
    ($dfg:ident, $insn:ident) => {
        if $dfg.inst_results($insn).len() != 1 {
            panic!("NYI Multple results for UnaryImm inst {}", $dfg[$insn].opcode())
        }
    };
}

macro_rules! ASSERT_NO_RESULT {
    ($dfg:ident, $insn:ident) => {
        if $dfg.inst_results($insn).len() != 0 {
            panic!("Instruction {} shouldn't return an explicit result", $dfg[$insn].opcode())
        }
    };
}

macro_rules! ASSERT_SAME_TYPE{
    ($typ1:ident, $typ2:ident) => {
        if $typ1!= $typ2 {
            panic!("Differing types: {} and {}", $typ1, $typ2)
        }
    };
}

macro_rules! ASSERT_SAME_SORT{
    ($sort1:ident, $sort2:ident) => {
        if $sort1!= $sort2 {
            panic!("Differing sorts: {} and {}", $sort1, $sort2)
        }
    };
}

macro_rules! ASSERT_SCALAR_TYPE {
    ($typ:expr) => {
        if $typ.lane_count() != 1 {
            panic!("Expected scalar type not {}", $typ)
        }
    };
}

macro_rules! ASSERT_MEMORY_ACCESS_SANE{
    ($z3_state:ident, $addr_type:ident, $res_type:ident) => {
        {
            if $addr_type.lane_count() != 1 {
                panic!("Vector sort used as address");
            }

            if $addr_type.bits() as u32 != $z3_state.addr_bits {
                panic!("Vector sort used as address");
            }

            let accessWidth = $res_type.bits() as u32;
            if accessWidth % $z3_state.val_bits != 0 {
                panic!("Access size {} not a multiple of memory cell size {}.",
                        accessWidth, $z3_state.val_bits);
            }

            if accessWidth <$z3_state.val_bits {
                panic!("Access size {} smaller than memory cell size {}.",
                        accessWidth, $z3_state.val_bits);
            }
        }


    }
}

impl<'ctx> Z3State<'ctx> {
    pub fn new(ctx: &'ctx Context) -> Z3State<'ctx> {
        let mut res: Z3State<'ctx> = Z3State{ ctx:ctx,
                 defs:HashMap::new(),
                 sorts:HashMap::new(),
                 def_order:vec!(),
                 val_to_ssa_name: HashMap::new(),
                 addr_bits: 32,
                 val_bits: 8,
                 mem_ssa_ctr: 0,
        };

        let mem_sort = ctx.array_sort(&ctx.bitvector_sort(res.addr_bits),
                                      &ctx.bitvector_sort(res.val_bits));
        let mem = ctx.named_const("mem", &mem_sort);
        let mut curC: u64;
        {
            curC = res.mem_ssa_ctr;
        }
        res.define_int(Z3SSAVal::Memory(curC), mem, mem_sort);

        res
    }

    fn lookup_int(&self, v: Z3SSAVal, sort: Option<&Sort<'ctx>>) -> Ast<'ctx> {
        match self.val_to_ssa_name.get(&v) {
            Some(name) => {
                let defined_sort = self.sorts.get(&v)
                    .expect("Definition without sort in Z3State");
                if let Some(req_sort) = sort {
                    if defined_sort != req_sort {
                        panic!("Lookup of {} returned type {}, expected {}.",
                               name, defined_sort, req_sort);
                    }
                }
                Ast::new_const(&self.ctx.str_sym(name.as_str()), defined_sort)
            },
            None => {
                match v {
                    Z3SSAVal::CtonVal(cv) => panic!("Looking up non-existend C-ton Val {}", (cv)),
                    Z3SSAVal::Memory(ind) => panic!("Looking up non-existant memory_{}", ind),
                }
            }
        }
    }

    fn lookup(&self, cval: Value, sort: &Sort<'ctx>) -> Ast<'ctx> {
        self.lookup_int(Z3SSAVal::CtonVal(cval), Some(sort))
    }

    fn lookup_mem(&self) -> Ast<'ctx> {
        self.lookup_int(Z3SSAVal::Memory(self.mem_ssa_ctr), None)
    }

    fn define_int(&mut self, v: Z3SSAVal, val: Ast<'ctx>, sort: Sort<'ctx>) -> () {
        if let Some(old_name) = self.val_to_ssa_name.get(&v) {
            panic!("Redefining existing name {}. SSA Violated.", old_name);
        }

        let num_defs;
        {
            num_defs = self.defs.len();
        }

        let ssa_name = match v {
            Z3SSAVal::CtonVal(v) => "ssa_".to_string() + num_defs.to_string().as_str(),
            Z3SSAVal::Memory(ind) => "mem_".to_string() + ind.to_string().as_str(),
        };

        println!("Defining {}:={}", ssa_name, &val);

        self.defs.insert(v, val);
        self.sorts.insert(v, sort);
        self.def_order.push(v);
        self.val_to_ssa_name.insert(v, ssa_name);
    }

    fn define(&mut self, cval: Value, val: Ast<'ctx>, sort: Sort<'ctx>) -> () {
        self.define_int(Z3SSAVal::CtonVal(cval), val, sort);
    }

    fn bin_opcode_to_z3op(op: Opcode) -> Z3BinOps {
        match op {
            // Normal Binary Instrs
            Opcode::Iadd => (Z3BinOps::BVAdd),
            Opcode::Isub => (Z3BinOps::BVSub),
            Opcode::Imul => (Z3BinOps::BVMul),
            Opcode::Udiv => (Z3BinOps::BVUdiv),
            Opcode::Sdiv => (Z3BinOps::BVSdiv),
            Opcode::Urem => (Z3BinOps::BVUrem),
            Opcode::Srem => (Z3BinOps::BVSrem),
            Opcode::Band => (Z3BinOps::BVAnd),
            Opcode::Bor => (Z3BinOps::BVOr),
            Opcode::Bxor => (Z3BinOps::BVXor),
            Opcode::Ishl => (Z3BinOps::BVShl),
            Opcode::Ushr => (Z3BinOps::BVLshr),
            Opcode::Sshr => (Z3BinOps::BVAshr),
            // Binary Instrs with Immediate operands
            // Modeled with the same z3 ops
            Opcode::IaddImm => (Z3BinOps::BVAdd),
            Opcode::ImulImm => (Z3BinOps::BVMul),
            Opcode::UdivImm => (Z3BinOps::BVUdiv),
            Opcode::SdivImm => (Z3BinOps::BVSdiv),
            Opcode::UremImm => (Z3BinOps::BVUrem),
            Opcode::SremImm => (Z3BinOps::BVSrem),
            Opcode::BandImm => (Z3BinOps::BVAnd),
            Opcode::BorImm => (Z3BinOps::BVOr),
            Opcode::BxorImm => (Z3BinOps::BVXor),
            _ => panic!("Unknown instruction opcode {}", op)
        }
    }

    fn z3_lanewise_binop(&self,
                         lhs: Ast<'ctx>,
                         rhs: Ast<'ctx>,
                         op: &Z3BinOps,
                         sort: &Sort,
                         nlanes: u32,
                         lane_bits: u32) -> Ast<'ctx> {
        // Assert nlanes*lane_bits = width(sort)
        if self.ctx.bitvector_sort(nlanes * lane_bits) != *sort {
            panic!("Mismatch between expected z3 sort and nlanes*lane_bits");
        }
        // If nlanes == 1 return basic op
        if nlanes == 1 {
            match *op {
                Z3BinOps::BVAdd => lhs.bvadd(&rhs),
                Z3BinOps::BVSub => lhs.bvsub(&rhs),
                Z3BinOps::BVMul => lhs.bvmul(&rhs),
                Z3BinOps::BVUdiv=> lhs.bvudiv(&rhs),
                Z3BinOps::BVSdiv=> lhs.bvsdiv(&rhs),
                Z3BinOps::BVUrem=> lhs.bvurem(&rhs),
                Z3BinOps::BVSrem=> lhs.bvsrem(&rhs),
                Z3BinOps::BVAnd => lhs.bvand(&rhs),
                Z3BinOps::BVOr => lhs.bvor(&rhs),
                Z3BinOps::BVXor => lhs.bvxor(&rhs),
                Z3BinOps::BVShl => lhs.bvshl(&rhs),
                Z3BinOps::BVLshr => lhs.bvlshr(&rhs),
                Z3BinOps::BVAshr => lhs.bvashr(&rhs),
            }
        } else {
        // Else apply op recursively to each lane, and concat results
            let mut lane_res : Vec<Ast<'ctx>> = vec!();
            let lane_sort : Sort<'ctx> = self.ctx.bitvector_sort(lane_bits);

            // Concat(i,j) puts i at the MSB and j as LSB so iterate MSB->LSB
            for i in nlanes-1..0 {
                let lhs1: Ast<'ctx> = lhs.extract((i+1)*8-1, i*8);
                let rhs1: Ast<'ctx> = rhs.extract((i+1)*8-1, i*8);
                lane_res.push(self.z3_lanewise_binop(lhs1,
                                                     rhs1,
                                                     &op,
                                                     &lane_sort,
                                                     1,
                                                     lane_bits));
            }

            let mut res = lane_res[0].concat(&lane_res[1]);

            for i in 2..lane_res.len() {
                res = res.concat(&lane_res[i]);
            }
            res
        }
    }

    fn z3_bv_i64(&self,
              typ: Type,
              v: i64) -> (Ast<'ctx>, Sort<'ctx>) {
        let nbits = typ.bits() as u32;
        let sort = self.ctx.bitvector_sort(nbits);
        let z3_val = Ast::from_bv(self.ctx, v, nbits);
        (z3_val, sort)
    }

    fn z3_bv_val<T: Into<i64>>(&self,
              typ: Type,
              imm: T) -> (Ast<'ctx>, Sort<'ctx>) {
        self.z3_bv_i64(typ, imm.into())
    }


    fn z3_bv_imm(&self,
              typ: Type,
              imm: Imm64) -> (Ast<'ctx>, Sort<'ctx>) {
        self.z3_bv_val(typ, imm)
    }

    fn z3_bv_off(&self,
              typ: Type,
              off: Offset32) -> (Ast<'ctx>, Sort<'ctx>) {
        self.z3_bv_val(typ, off)
    }

    fn load_info(&self, op: Opcode, typ: &Type) -> (u32, u32, Option<Z3UnOps>) {
        let returnedSize : u32 = typ.bits() as u32;

        let loadedSize : u32 = match op {
            Opcode::Load => returnedSize,
            Opcode::Uload8 | Opcode::Sload8 => 8,
            Opcode::Uload16 | Opcode::Sload16 => 16,
            Opcode::Uload32 | Opcode::Sload32 => 32,
            _ => panic!("Not a load opcode: {}", op)
        };

        let extFun : Option<Z3UnOps> = match op {
            Opcode::Load => None,
            Opcode::Uload8 | Opcode::Uload16 | Opcode::Uload32 => Some(Z3UnOps::BVZeroExt),
            Opcode::Sload8 | Opcode::Sload16 | Opcode::Sload32 => Some(Z3UnOps::BVSignExt),
            _ => panic!("Not a load opcode: {}", op)
        };

        if let Some(_) = extFun {
            ASSERT_SCALAR_TYPE!(typ);
        };

        (loadedSize, returnedSize, extFun)
    }

    fn store_info(&self, op: Opcode, typ: &Type) -> (u32, u32) {
        let argSize : u32 = typ.bits() as u32;

        let storedSize : u32 = match op {
            Opcode::Store => argSize,
            Opcode::Istore8 => 8,
            Opcode::Istore16 => 16,
            Opcode::Istore32 => 32,
            _ => panic!("Not a store opcode: {}", op)
        };

        (storedSize, argSize)
    }

    pub fn add_instr(&mut self, dfg: &DataFlowGraph, insn: Inst) -> () {
        match dfg[insn] {
            InstructionData::UnaryImm { opcode, imm } => {
                ASSERT_SINGLE_RESULT!(dfg, insn);
                let r_value: Value = dfg.first_result(insn);
                let ret_type: Type = dfg.value_type(r_value);

                let (z3_val, z3_sort) = self.z3_bv_imm(ret_type, imm);

                match opcode {
                    /// `a = iconst N`. (UnaryImm)
                    Opcode::Iconst => {
                        self.define(r_value, z3_val, z3_sort);
                    }
                    _ => {
                        panic!("Unknown UnaryImm opcode {}", opcode);
                    }
                };
            }
            InstructionData::Binary { opcode, args } => {
                let r_value = dfg.first_result(insn);
                let arg_type: Type = dfg.value_type(args[0]);
                let arg2_type: Type = dfg.value_type(args[1]);
                let ret_type: Type = dfg.value_type(r_value);

                ASSERT_SINGLE_RESULT!(dfg, insn);
                ASSERT_SAME_TYPE!(arg_type, ret_type);
                ASSERT_SAME_TYPE!(arg_type, arg2_type);

                let arg_sort = to_z3_sort(self.ctx, &arg_type);
                let lhs = self.lookup(args[0], &arg_sort);
                let rhs = self.lookup(args[1], &arg_sort);
                let z3_op = Z3State::bin_opcode_to_z3op(opcode);

                let res = self.z3_lanewise_binop(lhs, rhs, &z3_op, &arg_sort,
                                arg_type.lane_count() as u32,
                                arg_type.lane_bits() as u32);

                self.define(r_value, res, arg_sort);
            }
            InstructionData::BinaryImm { opcode, arg, imm } => {
                let r_value = dfg.first_result(insn);
                let arg_type: Type = dfg.value_type(arg);
                let ret_type: Type = dfg.value_type(r_value);

                ASSERT_SINGLE_RESULT!(dfg, insn);
                ASSERT_SAME_TYPE!(arg_type, ret_type);

                let arg_sort = to_z3_sort(self.ctx, &arg_type);
                let lhs = self.lookup(arg, &arg_sort);
                // TODO: Here assuming that 64bit immediate is ALWAYS truncated to
                // first argument type. VERIFY THIS ASSUMPTION.
                let (rhs, _) = self.z3_bv_imm(arg_type, imm);
                let z3_op = Z3State::bin_opcode_to_z3op(opcode);
                let res = self.z3_lanewise_binop(lhs, rhs, &z3_op, &arg_sort,
                                arg_type.lane_count() as u32,
                                arg_type.lane_bits() as u32);

                self.define(r_value, res, arg_sort);
            }

            InstructionData::Store { opcode, flags, args, offset } => {
                let val = args[0];
                let addr = args[1];
                let addr_type: Type = dfg.value_type(addr);
                let val_type: Type = dfg.value_type(val);

                ASSERT_NO_RESULT!(dfg, insn);
                ASSERT_MEMORY_ACCESS_SANE!(self, addr_type, val_type);
                let (storedSize, argSize) = self.store_info(opcode, &val_type);

                let addr_sort = to_z3_sort(self.ctx, &addr_type);
                let arg_sort = to_z3_sort(self.ctx, &val_type);

                let z3_addr = self.lookup(addr, &addr_sort);
                let mut z3_arg = self.lookup(val, &arg_sort);

                let nCells = storedSize / self.val_bits;
                let (z3_off, z3_sort) = self.z3_bv_off(addr_type, offset);
                let z3_base_addr = z3_addr.bvadd(&z3_off);

                let mut mem = self.lookup_mem();

                for i in 0..nCells {
                    // Again this assumes little endian
                    let storeVal = z3_arg.extract((i+1)*self.val_bits-1, i *self.val_bits);
                    let (cellAddr, _) = self.z3_bv_i64(addr_type, i as i64);
                    let storeAddr = z3_base_addr.bvadd(&cellAddr);
                    mem = mem.store(&storeAddr, &storeVal);
                }

                let mem_sort = self.ctx.array_sort(&self.ctx.bitvector_sort(self.addr_bits),
                                                   &self.ctx.bitvector_sort(self.val_bits));
                self.mem_ssa_ctr+=1;
                let curC: u64;
                {
                    curC = self.mem_ssa_ctr;
                }
                self.define_int(Z3SSAVal::Memory(curC), mem, mem_sort);
            }

            InstructionData::Load { opcode, flags, arg, offset } => {
                let r_value = dfg.first_result(insn);
                let addr_type: Type = dfg.value_type(arg);
                let ret_type: Type = dfg.value_type(r_value);

                ASSERT_SINGLE_RESULT!(dfg, insn);
                let addr_sort = to_z3_sort(self.ctx, &addr_type);
                let ret_sort = to_z3_sort(self.ctx, &ret_type);
                let z3_base_addr = self.lookup(arg, &addr_sort);
                let mem = self.lookup_mem();
                let (z3_off, z3_off_sort) = self.z3_bv_off(addr_type, offset);
                ASSERT_SAME_SORT!(addr_sort, z3_off_sort);
                let z3_addr = z3_base_addr.bvadd(&z3_off);
                // Build the required value from memory cell-sized selects
                ASSERT_MEMORY_ACCESS_SANE!(self, addr_type, ret_type);
                let (accessWidth, retW, extOp) = self.load_info(opcode, &ret_type);
                // Assuming little endian TODO(dimo): Should this be generalized?
                let nCells = accessWidth / self.val_bits;
                let mut z3_val = mem.select(&z3_addr.bvadd(&self.z3_bv_i64(addr_type,
                                                                         (nCells-1) as i64).0));

                if nCells >= 2 {
                    for i in (0..nCells-1).rev() {
                        let cell = mem.select(&z3_addr.bvadd(&self.z3_bv_i64(addr_type, i as i64).0));
                        z3_val = z3_val.concat(&cell);
                }
                }
                z3_val = match extOp {
                    None=>z3_val,
                    Some(Z3UnOps::BVSignExt) => z3_val.sign_extend(retW - accessWidth),
                    Some(Z3UnOps::BVZeroExt) => z3_val.zero_extend(retW - accessWidth),
                    _ => panic!("unexpected")
                };
                self.define(r_value, z3_val, ret_sort);
            }
            InstructionData::MultiAry { opcode, .. } => {
                // TODO
                println!("Unexpected op: {}", opcode);
            }
            _ => {
                panic!("Unknown instruction format for {}", dfg[insn].opcode());
            }
        };
    }
}
