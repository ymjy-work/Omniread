package com.omniread.billing;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface PurchaseRecordMapper {

	@Insert("INSERT INTO purchase_record(user_id, plan, amount, balance_after, created_at) "
			+ "VALUES(#{userId}, #{plan}, #{amount}, #{balanceAfter}, #{createdAt})")
	int insert(@Param("userId") long userId, @Param("plan") String plan,
			@Param("amount") double amount, @Param("balanceAfter") double balanceAfter,
			@Param("createdAt") String createdAt);
}
