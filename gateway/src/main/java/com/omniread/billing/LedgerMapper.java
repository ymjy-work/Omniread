package com.omniread.billing;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 余额与积分流水：amount 为变动量（扣减为负），balance_after 为变动后值。 */
@Mapper
public interface LedgerMapper {

	@Insert("INSERT INTO balance_ledger(user_id, type, amount, balance_after, ref, created_at) "
			+ "VALUES(#{userId}, #{type}, #{amount}, #{balanceAfter}, #{ref}, #{createdAt})")
	int insertBalance(@Param("userId") long userId, @Param("type") String type,
			@Param("amount") double amount, @Param("balanceAfter") double balanceAfter,
			@Param("ref") String ref, @Param("createdAt") String createdAt);

	@Insert("INSERT INTO credit_ledger(user_id, type, amount, balance_after, ref, created_at) "
			+ "VALUES(#{userId}, #{type}, #{amount}, #{balanceAfter}, #{ref}, #{createdAt})")
	int insertCredit(@Param("userId") long userId, @Param("type") String type,
			@Param("amount") long amount, @Param("balanceAfter") long balanceAfter,
			@Param("ref") String ref, @Param("createdAt") String createdAt);
}
