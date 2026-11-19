package com.omniread.billing;

import java.util.List;

import com.omniread.billing.model.PlanCatalogEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface PlanCatalogMapper {

	@Select("SELECT * FROM plan_catalog ORDER BY price")
	List<PlanCatalogEntity> findAll();

	@Select("SELECT * FROM plan_catalog WHERE code = #{code}")
	PlanCatalogEntity findByCode(@Param("code") String code);
}
